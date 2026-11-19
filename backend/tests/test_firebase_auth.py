"""Exercise Firebase trust boundaries offline; never create cloud users or send mail."""
import asyncio
import json
import os
import time
import unittest
from unittest.mock import patch, Mock, AsyncMock
from uuid import uuid4

from firebase_admin import auth
from fastapi import HTTPException
from backend import firebase_auth as managed
from backend.accounts import accounts, password_hash
from backend.tests._asgi_client import request_raw


class FirebaseAuthTests(unittest.TestCase):
    def setUp(self):
        # Each test gets its own rate-limit window; previous account-flow tests
        # intentionally use the same in-process client address.
        from backend.app import app
        from backend.access import AccountAccessMiddleware
        middleware = app.middleware_stack
        while middleware is not None:
            if isinstance(middleware, AccountAccessMiddleware):
                middleware.attempts.clear()
            middleware = getattr(middleware, 'app', None)
        self.env = patch.dict(os.environ, {'AUTH_PROVIDER': 'firebase'})
        self.env.start()
        self.app = patch.object(managed, 'admin_app', return_value=object())
        self.app.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.app.stop)

    def claims(self, **changes):
        suffix = uuid4().hex
        return {'uid': suffix, 'email': suffix+'@example.com', 'email_verified': True,
                'auth_time': time.time(), 'name': 'Managed GM', **changes}

    def test_verified_login_creates_secure_session_and_preserves_campaign_access(self):
        claims = self.claims()
        with patch.object(managed, 'api', return_value={'idToken': 'firebase-id'}), \
             patch.object(auth, 'verify_id_token', return_value=claims), \
             patch.object(auth, 'create_session_cookie', return_value='firebase-session') as issue, \
             patch.object(auth, 'verify_session_cookie', return_value=claims) as verify:
            async def scenario():
                code, headers, raw = await request_raw('POST', '/v1/auth/login', body={'email': claims['email'], 'password': 'strong-password'})
                self.assertEqual(code, 200, raw)
                user = json.loads(raw)['data']
                self.assertIn('HttpOnly', headers['set-cookie'])
                self.assertIn('SameSite=lax', headers['set-cookie'])
                cookie = {'cookie': headers['set-cookie'].split(';')[0]}
                code, _, raw = await request_raw('POST', '/v1/campaigns', body={'name': 'Managed world'}, headers=cookie)
                self.assertEqual(code, 201, raw)
                campaign = json.loads(raw)['data']
                self.assertEqual(campaign['owner']['id'], user['id'])
                code, _, _ = await request_raw('GET', '/v1/campaigns/'+campaign['campaignId'], headers=cookie)
                self.assertEqual(code, 200)
                other = self.claims()
                managed.bind_account(other)
                with patch.object(auth, 'verify_session_cookie', return_value=other):
                    with accounts.transaction() as sql:
                        import hashlib
                        sql('INSERT INTO account_sessions(token_hash,user_id,expires_at) VALUES (%s,%s,%s)',
                            (hashlib.sha256(b'other-cookie').hexdigest(), managed.bind_account(other)['id'], time.time()+3600))
                    code, _, _ = await request_raw('GET', '/v1/campaigns/'+campaign['campaignId'], headers={'cookie': 'session_smith=other-cookie'})
                    self.assertEqual(code, 404)
                # Password reset or admin revocation must invalidate a copied cookie.
                with patch.object(auth, 'verify_session_cookie', side_effect=auth.RevokedSessionCookieError('revoked')):
                    code, _, _ = await request_raw('GET', '/v1/auth/me', headers=cookie)
                    self.assertEqual(code, 401)
                with patch.object(auth, 'revoke_refresh_tokens') as revoke:
                    code, _, _ = await request_raw('POST', '/v1/auth/logout', body={}, headers=cookie)
                    self.assertEqual(code, 200)
                    revoke.assert_called_once_with(claims['uid'], app=managed.admin_app())
                # Firebase may still validate a same-second token; the allowlist
                # must nevertheless reject every copied logged-out cookie.
                code, _, _ = await request_raw('GET', '/v1/auth/me', headers=cookie)
                self.assertEqual(code, 401)
            asyncio.run(scenario())
            issue.assert_called_once()
            self.assertTrue(all(call.kwargs['check_revoked'] for call in verify.call_args_list))

    def test_unverified_and_forged_tokens_never_issue_sessions(self):
        async def scenario():
            with patch.object(managed, 'api', return_value={'idToken': 'untrusted'}), \
                 patch.object(auth, 'create_session_cookie') as issue:
                for result in [self.claims(email_verified=False), self.claims(auth_time=0)]:
                    with patch.object(auth, 'verify_id_token', return_value=result):
                        code, headers, _ = await request_raw('POST', '/v1/auth/login', body={'email': result['email'], 'password': 'strong-password'})
                        self.assertIn(code, (401, 403))
                        self.assertNotIn('set-cookie', headers)
                with patch.object(auth, 'verify_id_token', side_effect=auth.InvalidIdTokenError('forged')):
                    code, _, _ = await request_raw('POST', '/v1/auth/login', body={'email': 'test@example.com', 'password': 'strong-password'})
                    self.assertEqual(code, 401)
                issue.assert_not_called()
        asyncio.run(scenario())

    def test_email_collision_does_not_claim_legacy_account(self):
        claims = self.claims()
        local_id = uuid4().hex
        with accounts.transaction() as sql:
            sql('INSERT INTO app_users(id,email,name,password_hash) VALUES (%s,%s,%s,%s)',
                (local_id, claims['email'], 'Legacy', password_hash('strong-password')))
        with self.assertRaises(HTTPException) as caught:
            managed.bind_account(claims)
        self.assertEqual(caught.exception.status_code, 409)
        with accounts.transaction() as sql:
            sql('INSERT INTO firebase_identities(uid,user_id) VALUES (%s,%s)', (claims['uid'], local_id))
        self.assertEqual(managed.bind_account(claims)['id'], local_id)
        self.assertEqual(managed.bind_account({**claims, 'email': 'new-'+claims['email']})['id'], local_id)

    def test_signup_verification_and_recovery_do_not_issue_session(self):
        async def scenario():
            with patch.object(managed, 'api', return_value={'idToken': 'new-id'}) as api:
                code, headers, raw = await request_raw('POST', '/v1/auth/register', body={'name': 'New', 'email': uuid4().hex+'@example.com', 'password': 'strong-password'})
                self.assertEqual(code, 200)
                self.assertTrue(json.loads(raw)['data']['verificationRequired'])
                self.assertNotIn('set-cookie', headers)
                self.assertEqual(api.call_args_list[-1].args, ('sendOobCode', {'requestType': 'VERIFY_EMAIL', 'idToken': 'new-id'}))
            results = []
            for failure in (None, managed.FirebaseRequestError('EMAIL_NOT_FOUND', 'unknown account')):
                with patch.object(managed, 'api', side_effect=failure, return_value={}):
                    code, headers, raw = await request_raw('POST', '/v1/auth/forgot-password', body={'email': 'test@example.com'})
                    self.assertEqual(code, 200)
                    self.assertNotIn('set-cookie', headers)
                    results.append(raw)
            self.assertEqual(results[0], results[1])
            code, _, _ = await request_raw('POST', '/v1/auth/forgot-password', body={'email': 'test@example.com'}, headers={'origin': 'https://attacker.example'})
            self.assertEqual(code, 403)
        asyncio.run(scenario())

    def test_google_token_is_exchanged_for_firebase_session(self):
        from backend import auth as google
        token = {'id_token': 'google-id'}
        with patch.object(google, 'OAUTH_CONFIGURED', True), \
             patch.object(google.oauth.google, 'authorize_access_token', AsyncMock(return_value=token)), \
             patch.object(managed, 'api', return_value={'idToken': 'firebase-id'}) as api, \
             patch.object(auth, 'verify_id_token', return_value=self.claims()), \
             patch.object(auth, 'create_session_cookie', return_value='firebase-cookie'):
            code, headers, _ = asyncio.run(request_raw('GET', '/auth/google/callback'))
            self.assertEqual(code, 307)
            self.assertIn('firebase-cookie', headers['set-cookie'])
            self.assertEqual(api.call_args.args[0], 'signInWithIdp')
            self.assertIn('providerId=google.com', api.call_args.args[1]['postBody'])

    def test_local_cookie_cannot_authenticate_in_firebase_mode(self):
        with patch.object(auth, 'verify_session_cookie', side_effect=ValueError('invalid')):
            self.assertIsNone(accounts.user_for_token('old-local-session'))

    def test_migration_keeps_uid_google_identity_and_scrypt_parameters(self):
        from backend.migrate_firebase_users import migrate
        suffix = uuid4().hex
        hashed = password_hash('preserved-password')
        row = {'id': suffix, 'email': suffix+'@example.com', 'name': 'GM', 'password_hash': hashed, 'subject': 'google-sub'}
        sql = Mock()
        sql.return_value.fetchall.return_value = [row]
        sql.return_value.fetchone.return_value = None
        from contextlib import contextmanager
        @contextmanager
        def transaction():
            yield sql
        with patch.object(accounts, 'transaction', transaction), \
             patch('backend.migrate_firebase_users.admin_app', return_value=object()), \
             patch.object(auth, 'get_user_by_email', side_effect=auth.UserNotFoundError('missing')), \
             patch.object(auth, 'get_user', side_effect=auth.UserNotFoundError('missing')), \
             patch.object(auth, 'import_users', return_value=Mock(failure_count=0)) as importing:
            migrate(False)
            importing.assert_not_called()
            migrate(True)
            record = importing.call_args.args[0][0]
            self.assertEqual(record.uid, suffix)
            self.assertEqual(record.password_hash, bytes.fromhex(hashed.split(':')[1]))
            self.assertEqual(record.provider_data[0].uid, 'google-sub')
            hashing = importing.call_args.kwargs['hash_alg']
            self.assertIsNotNone(hashing)

    def test_recovery_is_rate_limited(self):
        async def scenario():
            with patch.object(managed, 'api', return_value={}) as api:
                for _ in range(20):
                    code, _, _ = await request_raw('POST', '/v1/auth/forgot-password', body={'email': 'test@example.com'})
                    self.assertEqual(code, 200)
                code, _, _ = await request_raw('POST', '/v1/auth/forgot-password', body={'email': 'test@example.com'})
                self.assertEqual(code, 429)
                self.assertEqual(api.call_count, 20)
        asyncio.run(scenario())

    def test_explicit_google_link_uses_current_identity_and_requires_recent_login(self):
        from starlette.requests import Request
        claims = self.claims()
        local = managed.bind_account(claims)
        request = Request({'type': 'http', 'scheme': 'http', 'path': '/', 'headers': [],
                           'server': ('test', 80), 'session': {'firebase_link_uid': claims['uid']}})
        google = {'id_token': 'google-id', 'userinfo': {'email': claims['email'], 'email_verified': True}}
        with patch.object(managed, 'user_for_cookie', return_value=local), \
             patch.object(auth, 'verify_session_cookie', return_value=claims), \
             patch.object(auth, 'create_custom_token', return_value=b'custom'), \
             patch.object(auth, 'verify_id_token', return_value=claims), \
             patch.object(auth, 'create_session_cookie', return_value='linked'), \
             patch.object(managed, 'google_uid_connected', return_value=False), \
             patch.object(managed, 'api', side_effect=[{'idToken': 'current-user'}, {'idToken': 'linked-user'}]) as api:
            result = managed.google_login(google, request)
            self.assertEqual(result.status_code, 307)
            self.assertEqual(api.call_args_list[1].args[1]['idToken'], 'current-user')
            self.assertEqual(managed.bind_account(claims)['id'], local['id'])
        request.session['firebase_link_uid'] = claims['uid']
        with patch.object(auth, 'verify_session_cookie', return_value={**claims, 'auth_time': 0}), \
             patch.object(managed, 'api') as api:
            with self.assertRaises(HTTPException) as caught:
                managed.google_login(google, request)
            self.assertEqual(caught.exception.status_code, 401)
            api.assert_not_called()

    def test_google_provider_status_uses_linked_provider_not_email(self):
        with patch.object(auth, 'get_user', return_value=Mock(provider_data=[Mock(provider_id='google.com')])):
            self.assertTrue(managed.google_uid_connected('firebase-user'))
        with patch.object(auth, 'get_user', return_value=Mock(provider_data=[Mock(provider_id='password')])):
            self.assertFalse(managed.google_uid_connected('firebase-user'))

    def test_already_linked_google_start_is_idempotent(self):
        from backend import auth as google
        from starlette.requests import Request
        request = Request({'type': 'http', 'headers': [], 'session': {}})
        with patch.object(google, 'OAUTH_CONFIGURED', True), \
             patch.object(accounts, 'user_for_token', return_value={'id': 'user'}), \
             patch.object(managed, 'google_connected', return_value=True), \
             patch.object(google.oauth.google, 'authorize_redirect', AsyncMock()) as redirect:
            result = asyncio.run(google.google_link(request))
            self.assertEqual(result.status_code, 307)
            redirect.assert_not_called()

    def test_migrated_google_verification_requires_matching_trusted_identity(self):
        claims = self.claims(email_verified=False, firebase={'sign_in_provider': 'google.com'})
        profile = {'sub': 'google-sub', 'email': claims['email'], 'email_verified': True}
        user = Mock(email=claims['email'], provider_data=[Mock(provider_id='google.com', uid='google-sub')])
        result = {'idToken': 'unverified', 'refreshToken': 'refresh'}
        with patch.object(auth, 'verify_id_token', return_value=claims), \
             patch.object(auth, 'get_user', return_value=user), \
             patch.object(auth, 'update_user') as update, \
             patch.object(managed, 'api', return_value={'id_token': 'verified'}) as api:
            self.assertEqual(managed.verified_google_token(result, profile), 'verified')
            update.assert_called_once_with(claims['uid'], email_verified=True, app=managed.admin_app())
            api.assert_called_once_with('refreshToken', {'refresh_token': 'refresh'})
        for bad in ({**profile, 'email_verified': False}, {**profile, 'sub': 'other-google'}, {**profile, 'email': 'other@example.com'}):
            with patch.object(auth, 'verify_id_token', return_value=claims), \
                 patch.object(auth, 'get_user', return_value=user), \
                 patch.object(auth, 'update_user') as update:
                with self.assertRaises(HTTPException):
                    managed.verified_google_token(result, bad)
                update.assert_not_called()

    def test_existing_short_password_can_reach_firebase_login(self):
        async def scenario():
            with patch.object(managed, 'password_login', return_value={'data': {'id': 'existing'}}) as login:
                code, _, _ = await request_raw('POST', '/v1/auth/login', body={'email': 'existing@example.com', 'password': 'short123'})
                self.assertEqual(code, 200)
                self.assertEqual(login.call_args.args[0].password, 'short123')
            code, _, _ = await request_raw('POST', '/v1/auth/register', body={'name': 'New', 'email': 'new@example.com', 'password': 'short123'})
            self.assertEqual(code, 422)
        asyncio.run(scenario())
