"""Behavior regressions from the code-quality review; no live provider calls."""
import asyncio
import json
import logging
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from backend import firebase_auth
from backend.db import postgres_enabled, connect
from backend.tests._asgi_client import request_raw


class QualityTests(unittest.TestCase):
    def test_recovery_does_not_hide_delivery_failures(self):
        for code in ('TOO_MANY_ATTEMPTS_TRY_LATER', 'OPERATION_NOT_ALLOWED', 'QUOTA_EXCEEDED'):
            with patch.object(firebase_auth, 'api', side_effect=firebase_auth.FirebaseRequestError(code, 'failure')):
                with self.assertRaises(HTTPException) as error:
                    firebase_auth.recovery('dummy@example.com')
                self.assertEqual(error.exception.status_code, 503)
        with patch.object(firebase_auth, 'api', side_effect=firebase_auth.FirebaseRequestError('EMAIL_NOT_FOUND', 'missing')):
            self.assertIn('If an account exists', firebase_auth.recovery('dummy@example.com')['data']['message'])

    def test_expired_logout_is_idempotent_but_rejects_cross_site_requests(self):
        async def scenario():
            code, headers, _ = await request_raw('POST', '/v1/auth/logout', body={}, headers={'cookie':'session_smith=expired'})
            self.assertEqual(code, 200)
            self.assertIn('Max-Age=0', headers['set-cookie'])
            code, _, _ = await request_raw('POST', '/v1/auth/logout', body={}, headers={'origin':'https://attacker.example'})
            self.assertEqual(code, 403)
        asyncio.run(scenario())

    def test_real_export_contains_saved_notes_and_entries_and_is_private(self):
        async def scenario():
            async def call(method, path, body=None, cookie='', expected=200):
                code, headers, raw = await request_raw(method,path,body=body,headers={'cookie':cookie})
                self.assertEqual(code,expected,raw)
                return json.loads(raw).get('data'), headers.get('set-cookie','').split(';')[0]
            suffix=uuid4().hex
            _, cookie=await call('POST','/v1/auth/register',{'name':'Export GM','email':suffix+'@example.com','password':'strong-password'})
            campaign,_=await call('POST','/v1/campaigns',{'name':'Actual persisted world'},cookie,201)
            cid=campaign['campaignId']
            await call('POST',f'/v1/campaigns/{cid}/entries',{'category':'economy','title':'Unique entry','note':'Saved durable content'},cookie,201)
            await call('POST',f'/v1/campaigns/{cid}/notes',{'content':'Unique raw note','sessionNumber':'1','startExtraction':False},cookie,202)
            exported,_=await call('GET',f'/v1/campaigns/{cid}/export',cookie=cookie)
            self.assertIn('Unique raw note',json.dumps(exported))
            self.assertIn('Saved durable content',json.dumps(exported))
            self.assertEqual(exported['campaign']['campaignId'],cid)
            _,other=await call('POST','/v1/auth/register',{'name':'Other','email':'other'+suffix+'@example.com','password':'strong-password'})
            await call('GET',f'/v1/campaigns/{cid}/export',cookie=other,expected=404)
            await call('PATCH',f'/v1/campaigns/{cid}',{'visibility':'shared','model':'premium'},cookie)
            sealed,_=await call('POST',f'/v1/campaigns/{cid}/seal-world',{},cookie)
            self.assertEqual(sealed['visibility'],'shared')
            self.assertEqual(sealed['model'],'premium')
        asyncio.run(scenario())

    def test_oauth_logging_redacts_credentials(self):
        from backend.request_logging import RedactOAuthQuery
        record=logging.LogRecord('uvicorn.access',logging.INFO,'',1,'%s %s %s %s %s',('client','GET','/auth/google/callback?code=secret&state=private','1.1',302),None)
        RedactOAuthQuery().filter(record)
        self.assertNotIn('secret',record.getMessage())
        self.assertNotIn('private',record.getMessage())

    def test_trusted_proxy_separates_rate_limit_clients(self):
        from backend.access import AccountAccessMiddleware
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
        async def endpoint(scope, receive, send):
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b''})
        app=ProxyHeadersMiddleware(AccountAccessMiddleware(endpoint),trusted_hosts='172.16.0.0/12')
        async def scenario():
            for index in range(25):
                messages=[]
                async def send(message): messages.append(message)
                async def receive(): return {'type':'http.request','body':b''}
                scope={'type':'http','method':'POST','path':'/v1/auth/login','scheme':'http','server':('test',80),'client':('172.18.0.3',1000),'query_string':b'',
                       'headers':[(b'host',b'test'),(b'content-type',b'application/json'),(b'x-forwarded-for',f'198.51.100.{index+1}'.encode())]}
                await app(scope,receive,send)
                self.assertEqual(messages[0]['status'],200)
        asyncio.run(scenario())

    @unittest.skipUnless(postgres_enabled(), 'Requires isolated PostgreSQL test database')
    def test_pooled_transactions_roll_back(self):
        user_id=uuid4().hex
        with self.assertRaises(RuntimeError):
            with connect() as connection:
                connection.execute('INSERT INTO app_users(id,email,name,password_hash) VALUES (%s,%s,%s,%s)',(user_id,user_id+'@example.com','Rollback','unused'))
                raise RuntimeError('abort')
        with connect() as connection:
            self.assertIsNone(connection.execute('SELECT id FROM app_users WHERE id=%s',(user_id,)).fetchone())
