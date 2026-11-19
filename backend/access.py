"""Enforce account and campaign access before dispatch, including indirect IDs."""
from collections import defaultdict, deque
import time

from starlette.requests import Request
from starlette.responses import JSONResponse
from backend.accounts import accounts, COOKIE
from backend.db import connect, postgres_enabled


class AccountAccessMiddleware:
    def __init__(self, app):
        self.app = app
        self.attempts = defaultdict(deque)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope['path'].startswith('/v1/') or scope['method'] == 'OPTIONS':
            return await self.app(scope, receive, send)
        request = Request(scope)
        path = scope['path']
        method = scope['method']

        async def reject(message, status):
            await JSONResponse({'error': {'code':'access_denied','message':message}}, status_code=status)(scope, receive, send)

        if method not in ('GET','HEAD'):
            origin = request.headers.get('origin')
            allowed = {str(request.base_url).rstrip('/'), 'http://localhost:5173', 'http://127.0.0.1:5173'}
            if (origin and origin not in allowed) or request.headers.get('sec-fetch-site') == 'cross-site':
                return await reject('Cross-site requests are not allowed.',403)
            if method in ('POST','PATCH') and request.headers.get('content-type','').split(';')[0] != 'application/json':
                return await reject('Use application/json.',415)
        if path in ('/v1/healthz','/v1/readyz'):
            return await self.app(scope, receive, send)
        if path in ('/v1/auth/login','/v1/auth/register') and method == 'POST':
            # Bound password hashing work per source address. Shared rate limiting
            # belongs at the ingress when running multiple API processes.
            now = time.time()
            key = (scope.get('client') or ('unknown',))[0]
            for old_key in list(self.attempts):
                if not self.attempts[old_key] or self.attempts[old_key][-1] < now-60:
                    del self.attempts[old_key]
            attempts = self.attempts[key]
            while attempts and attempts[0] < now-60:
                attempts.popleft()
            if len(attempts) >= 20:
                return await reject('Too many attempts. Try again in a minute.',429)
            attempts.append(now)
            return await self.app(scope, receive, send)
        # Database I/O and password hashing run outside the event loop.
        from starlette.concurrency import run_in_threadpool
        user = await run_in_threadpool(accounts.user_for_token, request.cookies.get(COOKIE))
        if not user:
            return await reject('Sign in to continue.',401)
        scope.setdefault('state',{})['user'] = user
        parts = path.strip('/').split('/')
        campaign_id = parts[2] if len(parts)>2 and parts[1]=='campaigns' else None
        if len(parts)>2 and parts[1] in ('jobs','memory-proposals'):
            campaign_id = await run_in_threadpool(self.indirect_campaign, parts[1],parts[2])
            if not campaign_id:
                return await reject('Resource not found.',404)
        if campaign_id:
            role = await run_in_threadpool(accounts.role,campaign_id,user['id'])
            if not role:
                return await reject('Campaign not found.',404)
            if role != 'owner':
                # Private GM notes, AI context, prep and proposals are owner-only.
                suffix = parts[3] if len(parts)>3 and parts[1]=='campaigns' else ''
                if method != 'GET' or parts[1] != 'campaigns' or suffix not in ('','members','canon-events'):
                    return await reject('This action requires the campaign owner.',403)
        return await self.app(scope, receive, send)

    @staticmethod
    def indirect_campaign(kind, resource_id):
        if postgres_enabled():
            table = 'ai_jobs' if kind == 'jobs' else 'memory_proposals'
            with connect() as connection:
                row = connection.execute(f'SELECT campaign_id FROM {table} WHERE id=%s',(resource_id,)).fetchone()
                return row['campaign_id'] if row else None
        from backend.app import store
        if kind == 'jobs':
            return (store.jobs.get(resource_id) or {}).get('campaignId')
        for campaign_id,state in store.states.items():
            if any(p['id']==resource_id for p in state['proposals']):
                return campaign_id
        return None
