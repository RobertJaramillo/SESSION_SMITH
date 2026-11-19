"""Google callbacks exercise real account sessions and campaign permissions offline."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import backend.auth as auth
from backend.tests._asgi_client import request_raw


class GoogleAccountTests(unittest.TestCase):
    def test_google_and_password_share_account_and_permissions(self):
        async def scenario():
            async def call(method, path, body=None, cookie=''):
                return await request_raw(method, path, body=body, headers={'cookie': cookie})

            suffix = uuid4().hex
            email = f'google-{suffix}@example.com'
            code, headers, raw = await call('POST', '/v1/auth/register',
                {'name': 'Existing GM', 'email': email, 'password': 'strong-test-password'})
            self.assertEqual(code, 200)
            account = json.loads(raw)['data']
            password_cookie = headers['set-cookie'].split(';')[0]
            code, _, raw = await call('POST', '/v1/campaigns', {'name': 'Google world'}, password_cookie)
            self.assertEqual(code, 201)
            campaign_id = json.loads(raw)['data']['campaignId']
            profile = {'sub': suffix, 'email': email.upper(), 'email_verified': True, 'name': 'Google GM'}
            with patch.object(auth, 'OAUTH_CONFIGURED', True), patch.object(
                auth.oauth.google, 'authorize_access_token', AsyncMock(return_value={'userinfo': profile})):
                # Password login is still public with Google configured.
                code, _, _ = await call('POST', '/v1/auth/login', {'email': email, 'password': 'strong-test-password'})
                self.assertEqual(code, 200)
                code, _, _ = await call('GET', '/auth/google/callback')
                self.assertEqual(code, 409)
                code, headers, _ = await call('GET', '/auth/google/callback', cookie=password_cookie)
            self.assertEqual(code, 307)
            self.assertEqual(headers['location'], '/')
            google_cookie = headers['set-cookie'].split(';')[0]
            code, _, raw = await call('GET', '/v1/auth/me', cookie=google_cookie)
            self.assertEqual(code, 200)
            self.assertEqual(json.loads(raw)['data']['id'], account['id'])
            code, _, _ = await call('GET', f'/v1/campaigns/{campaign_id}', cookie=google_cookie)
            self.assertEqual(code, 200)
            # Subject, not mutable profile email, identifies returning Google users.
            profile['email'] = f'changed-{suffix}@example.com'
            with patch.object(auth, 'OAUTH_CONFIGURED', True), patch.object(
                auth.oauth.google, 'authorize_access_token', AsyncMock(return_value={'userinfo': profile})):
                code, headers, _ = await call('GET', '/auth/google/callback')
            cookie = headers['set-cookie'].split(';')[0]
            code, _, raw = await call('GET', '/auth/me', cookie=cookie)
            self.assertEqual(json.loads(raw)['data']['id'], account['id'])
            code, _, _ = await call('POST', '/v1/auth/logout', {}, cookie)
            self.assertEqual(code, 200)
            code, _, _ = await call('GET', '/v1/auth/me', cookie=cookie)
            self.assertEqual(code, 401)
            code, _, _ = await call('GET', '/auth/me', cookie=cookie)
            self.assertEqual(code, 401)
        asyncio.run(scenario())

    def test_google_new_account_is_isolated_and_unverified_email_rejected(self):
        async def scenario():
            suffix = uuid4().hex
            profile = {'sub': suffix, 'email': f'{suffix}@example.com', 'email_verified': False}
            with patch.object(auth, 'OAUTH_CONFIGURED', True), patch.object(
                auth.oauth.google, 'authorize_access_token', AsyncMock(return_value={'userinfo': profile})):
                code, _, _ = await request_raw('GET', '/auth/google/callback')
                self.assertEqual(code, 401)
                profile['email_verified'] = True
                code, headers, _ = await request_raw('GET', '/auth/google/callback')
                self.assertEqual(code, 307)
            cookie = headers['set-cookie'].split(';')[0]
            code, _, raw = await request_raw('GET', '/v1/auth/me', headers={'cookie': cookie})
            self.assertEqual(code, 200)
            self.assertIn('id', json.loads(raw)['data'])
            code, _, _ = await request_raw('GET', '/v1/campaigns/campaign_ashes_of_kestrel_vale', headers={'cookie': cookie})
            self.assertEqual(code, 404)
            code, _, _ = await request_raw('POST', '/auth/logout', headers={'cookie': cookie, 'origin': 'https://attacker.example'})
            self.assertEqual(code, 403)
            code, _, _ = await request_raw('POST', '/auth/logout', headers={'cookie': cookie})
            self.assertEqual(code, 200)
            code, _, _ = await request_raw('GET', '/v1/auth/me', headers={'cookie': cookie})
            self.assertEqual(code, 401)
        asyncio.run(scenario())
