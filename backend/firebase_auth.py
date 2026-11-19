"""Firebase Authentication adapter. Provider tokens never reach browser storage.

AUTH_PROVIDER=firebase enables this adapter; local auth remains for offline dev.
"""
from datetime import timedelta
from functools import lru_cache
from threading import RLock
import logging
import os
import hashlib
import secrets
import time
from urllib.parse import urlencode

import httpx
from firebase_admin.exceptions import FirebaseError
from google.auth.exceptions import GoogleAuthError
from fastapi import HTTPException
from starlette.responses import JSONResponse


def enabled():
    provider = os.getenv('AUTH_PROVIDER', 'local')
    if provider not in ('local', 'firebase'):
        raise RuntimeError('AUTH_PROVIDER must be local or firebase')
    return provider == 'firebase'



_admin_lock = RLock()


@lru_cache
def admin_app():
    import firebase_admin
    project = os.getenv('FIREBASE_PROJECT_ID')
    if not project or not os.getenv('FIREBASE_WEB_API_KEY'):
        raise HTTPException(503, detail='Firebase authentication is not configured.')
    try:
        credential = firebase_admin.credentials.ApplicationDefault()
        credential.get_credential()
        with _admin_lock:
            try:
                return firebase_admin.get_app('session-smith')
            except ValueError:
                return firebase_admin.initialize_app(credential, options={'projectId': project}, name='session-smith')
    except (GoogleAuthError, ValueError, OSError):
        raise HTTPException(503, detail='Firebase administrator credentials are unavailable.') from None


class FirebaseRequestError(HTTPException):
    def __init__(self, code, message, status_code=400):
        self.provider_code = code
        super().__init__(status_code, detail=message)


def api(operation, payload):
    key = os.getenv('FIREBASE_WEB_API_KEY')
    if not key:
        raise HTTPException(503, detail='Firebase authentication is not configured.')
    try:
        if operation == 'refreshToken':
            response = httpx.post('https://securetoken.googleapis.com/v1/token', params={'key': key},
                                  data={'grant_type': 'refresh_token', **payload}, timeout=15)
        else:
            response = httpx.post('https://identitytoolkit.googleapis.com/v1/accounts:' + operation,
                                  params={'key': key}, json=payload, timeout=15)
    except httpx.HTTPError:
        raise HTTPException(503, detail='Sign-in service is temporarily unavailable.') from None
    if response.status_code >= 500:
        raise HTTPException(503, detail='Sign-in service is temporarily unavailable.')
    if not response.is_success:
        code = response.json().get('error', {}).get('message', '').split(' : ')[0]
        if code in ('EMAIL_NOT_FOUND', 'INVALID_PASSWORD', 'INVALID_LOGIN_CREDENTIALS'):
            raise FirebaseRequestError(code, 'Email or password is incorrect.', 401)
        messages = {
            'EMAIL_EXISTS': 'An account with this email already exists. Sign in or reset your password.',
            'TOO_MANY_ATTEMPTS_TRY_LATER': 'Too many attempts. Please try again later.',
            'WEAK_PASSWORD': 'Use a password with at least 12 characters.',
            'PASSWORD_DOES_NOT_MEET_REQUIREMENTS': 'Use a password with at least 12 characters (maximum 256).',
            'USER_DISABLED': 'This account is disabled.',
            'INVALID_EMAIL': 'Enter a valid email address.',
            'OPERATION_NOT_ALLOWED': 'This sign-in method is not enabled.',
            'INVALID_IDP_RESPONSE': 'Google sign-in could not be completed.',
            'FEDERATED_USER_ID_ALREADY_LINKED': 'This Google account is already connected to another account.',
            'PROVIDER_ALREADY_LINKED': 'Google is already connected to this account.',
            'CREDENTIAL_TOO_OLD_LOGIN_AGAIN': 'Sign in again before connecting Google.',
        }
        raise FirebaseRequestError(code, messages.get(code, 'Authentication could not be completed. Please try again.'))
    return response.json()


def bind_account(claims):
    """Bind by trusted Firebase UID only. Email matches require explicit migration."""
    from backend.accounts import accounts, uid, password_hash, validated_email
    from backend.db import postgres_enabled
    subject = claims['uid']
    email = validated_email(claims.get('email', ''))
    if claims.get('email_verified') is not True:
        raise HTTPException(403, detail={'code': 'email_verification_required', 'message': 'Verify your email before signing in. Check your inbox or resend verification.'})
    with accounts.transaction() as sql:
        if postgres_enabled():
            sql('LOCK TABLE app_users IN EXCLUSIVE MODE')
        row = sql('SELECT u.* FROM app_users u JOIN firebase_identities f ON f.user_id=u.id WHERE f.uid=%s', (subject,)).fetchone()
        if row:
            # A Firebase-verified email change is reflected without changing ownership.
            collision = sql('SELECT id FROM app_users WHERE email=%s AND id<>%s', (email, row['id'])).fetchone()
            if collision:
                raise HTTPException(409, detail='This email is already associated with another account.')
            sql('UPDATE app_users SET email=%s WHERE id=%s', (email, row['id']))
            return {**dict(row), 'email': email}
        if sql('SELECT id FROM app_users WHERE email=%s', (email,)).fetchone():
            raise HTTPException(409, detail='This existing account must be migrated before Firebase sign-in. Contact the app administrator.')
        user = {'id': uid(), 'name': str(claims.get('name') or email)[:80], 'email': email}
        sql('INSERT INTO app_users(id,email,name,password_hash) VALUES (%s,%s,%s,%s)',
            (user['id'], email, user['name'], password_hash(secrets.token_urlsafe(64))))
        sql('INSERT INTO firebase_identities(uid,user_id) VALUES (%s,%s)', (subject, user['id']))
        return user


def session(id_token, request, response=None):
    from firebase_admin import auth
    from backend.accounts import accounts, COOKIE, SESSION_SECONDS, public
    app = admin_app()
    try:
        claims = auth.verify_id_token(id_token, app=app, check_revoked=True)
        if time.time() - claims.get('auth_time', 0) > 300:
            raise HTTPException(401, detail='Please sign in again.')
        user = bind_account(claims)
        cookie = auth.create_session_cookie(id_token, expires_in=timedelta(seconds=SESSION_SECONDS), app=app)
    except (ValueError, auth.InvalidIdTokenError, auth.RevokedIdTokenError, auth.UserDisabledError):
        raise HTTPException(401, detail='Please sign in again.') from None
    except (FirebaseError, GoogleAuthError):
        raise HTTPException(503, detail='Sign-in service is temporarily unavailable.') from None
    # A local allowlist makes logout immediate even when Firebase's revocation
    # timestamp and token auth_time fall within the same second.
    with accounts.transaction() as sql:
        sql('DELETE FROM account_sessions WHERE expires_at<%s', (time.time(),))
        old = request.cookies.get(COOKIE, '')
        sql('DELETE FROM account_sessions WHERE token_hash=%s', (hashlib.sha256(old.encode()).hexdigest(),))
        sql('INSERT INTO account_sessions(token_hash,user_id,expires_at) VALUES (%s,%s,%s) ON CONFLICT(token_hash) DO UPDATE SET expires_at=excluded.expires_at',
            (hashlib.sha256(cookie.encode()).hexdigest(), user['id'], time.time()+SESSION_SECONDS))
    if response is None:
        response = JSONResponse({'data': public(user)})
    from backend.session_cookies import set_session_cookie
    set_session_cookie(response, request, COOKIE, cookie, SESSION_SECONDS)
    return response


def user_for_cookie(cookie):
    if not cookie:
        return None
    from firebase_admin import auth
    from backend.accounts import accounts
    try:
        claims = auth.verify_session_cookie(cookie, app=admin_app(), check_revoked=True)
    except (ValueError, auth.InvalidSessionCookieError, auth.RevokedSessionCookieError, auth.UserDisabledError):
        return None
    except (FirebaseError, GoogleAuthError):
        raise HTTPException(503, detail='Sign-in service is temporarily unavailable.') from None
    if not claims.get('email_verified'):
        return None
    with accounts.transaction() as sql:
        row = sql('SELECT u.* FROM app_users u JOIN firebase_identities f ON f.user_id=u.id JOIN account_sessions s ON s.user_id=u.id WHERE f.uid=%s AND s.token_hash=%s AND s.expires_at>%s', (claims['uid'], hashlib.sha256(cookie.encode()).hexdigest(), time.time())).fetchone()
        return dict(row) if row else None


def password_login(payload, request):
    result = api('signInWithPassword', {'email': payload.email, 'password': payload.password, 'returnSecureToken': True})
    return session(result['idToken'], request)


def register(payload):
    from backend.accounts import accounts
    with accounts.transaction() as sql:
        if sql('SELECT id FROM app_users WHERE email=%s', (payload.email,)).fetchone():
            raise HTTPException(409, detail='An account with this email already exists. Sign in or reset your password.')
    result = api('signUp', {'email': payload.email, 'password': payload.password, 'returnSecureToken': True})
    api('update', {'idToken': result['idToken'], 'displayName': payload.name})
    api('sendOobCode', {'requestType': 'VERIFY_EMAIL', 'idToken': result['idToken']})
    return {'data': {'verificationRequired': True, 'message': 'Check your inbox to verify your email, then sign in.'}}


def recovery(email):
    # Never disclose whether an address exists. Firebase must also have email
    # enumeration protection enabled (documented in the setup guide).
    try:
        api('sendOobCode', {'requestType': 'PASSWORD_RESET', 'email': email})
    except FirebaseRequestError as error:
        if error.provider_code not in ('EMAIL_NOT_FOUND', 'INVALID_PASSWORD', 'INVALID_LOGIN_CREDENTIALS'):
            logging.getLogger(__name__).warning('Firebase email operation rejected: %s', error.provider_code)
            raise HTTPException(503, detail='Email delivery is temporarily unavailable. Please try again later.') from None
    return {'data': {'message': 'If an account exists for that email, a password reset link has been sent.'}}


def resend(payload):
    try:
        result = api('signInWithPassword', {'email': payload.email, 'password': payload.password, 'returnSecureToken': True})
        api('sendOobCode', {'requestType': 'VERIFY_EMAIL', 'idToken': result['idToken']})
    except FirebaseRequestError as error:
        if error.provider_code not in ('EMAIL_NOT_FOUND', 'INVALID_PASSWORD', 'INVALID_LOGIN_CREDENTIALS'):
            logging.getLogger(__name__).warning('Firebase email operation rejected: %s', error.provider_code)
            raise HTTPException(503, detail='Email delivery is temporarily unavailable. Please try again later.') from None
    return {'data': {'message': 'If the details are correct, a verification email has been sent.'}}


def google_connected(user_id):
    """Read linked providers from Firebase, rather than infer from email."""
    from backend.accounts import accounts
    with accounts.transaction() as sql:
        identity = sql('SELECT uid FROM firebase_identities WHERE user_id=%s', (user_id,)).fetchone()
    if not identity:
        return False
    return google_uid_connected(identity['uid'])


def google_uid_connected(firebase_uid):
    from firebase_admin import auth
    try:
        user = auth.get_user(firebase_uid, app=admin_app())
        return any(provider.provider_id == 'google.com' for provider in user.provider_data)
    except (FirebaseError, GoogleAuthError):
        raise HTTPException(503, detail='Could not check connected accounts. Please try again.') from None


def google_login(token, request):
    from backend.auth import OAUTH_REDIRECT_URI
    payload = {'postBody': urlencode({'id_token': token['id_token'], 'providerId': 'google.com'}),
        'requestUri': OAUTH_REDIRECT_URI, 'returnSecureToken': True, 'returnIdpCredential': False}
    linking = request.session.pop('firebase_link_uid', None)
    if linking:
        from firebase_admin import auth
        # The OAuth handshake must return to the same recently authenticated user.
        claims = recent_session(request)
        if claims['uid'] != linking:
            raise HTTPException(403, detail='Sign in again before connecting Google.')
        if google_uid_connected(linking):
            from starlette.responses import RedirectResponse
            request.session.clear()
            return RedirectResponse('/')
        profile = token.get('userinfo') or {}
        if profile.get('email_verified') is not True or str(profile.get('email', '')).lower() != str(claims.get('email', '')).lower():
            raise HTTPException(409, detail='Choose the Google account with your current account email.')
        custom = auth.create_custom_token(linking, app=admin_app())
        identity = api('signInWithCustomToken', {'token': custom.decode() if isinstance(custom, bytes) else custom, 'returnSecureToken': True})
        payload['idToken'] = identity['idToken']
    result = api('signInWithIdp', payload)
    from starlette.responses import RedirectResponse
    request.session.clear()
    return session(verified_google_token(result, token.get('userinfo') or {}), request, RedirectResponse('/'))


def logout(request):
    from backend.accounts import accounts, COOKIE
    from firebase_admin import auth
    # Revoke all Firebase sessions for this account, including other browsers.
    cookie = request.cookies.get(COOKIE)
    if cookie:
        with accounts.transaction() as sql:
            sql('DELETE FROM account_sessions WHERE token_hash=%s', (hashlib.sha256(cookie.encode()).hexdigest(),))
        try:
            claims = auth.verify_session_cookie(cookie, app=admin_app(), check_revoked=True)
            auth.revoke_refresh_tokens(claims['uid'], app=admin_app())
            with accounts.transaction() as sql:
                sql('DELETE FROM account_sessions WHERE user_id IN (SELECT user_id FROM firebase_identities WHERE uid=%s)', (claims['uid'],))
        except (ValueError, auth.InvalidSessionCookieError, auth.RevokedSessionCookieError, auth.UserDisabledError):
            pass
        except (FirebaseError, GoogleAuthError, HTTPException):
            logging.getLogger(__name__).warning('Remote logout revocation unavailable; local session revoked.')
    response = JSONResponse({'data': None})
    response.delete_cookie(COOKIE)
    return response


def recent_session(request):
    from firebase_admin import auth
    from backend.accounts import COOKIE
    try:
        claims = auth.verify_session_cookie(request.cookies.get(COOKIE, ''), app=admin_app(), check_revoked=True)
    except (ValueError, auth.InvalidSessionCookieError, auth.RevokedSessionCookieError, auth.UserDisabledError):
        raise HTTPException(401, detail='Sign in again before connecting Google.') from None
    if not user_for_cookie(request.cookies.get(COOKIE)) or time.time() - claims.get('auth_time', 0) > 300:
        raise HTTPException(401, detail='Sign in again before connecting Google.')
    return claims


def verified_google_token(result, profile):
    """Repair migrated Google accounts only after independent identity checks.

    Imported accounts intentionally start unverified. Firebase can retain that
    flag on Google sign-in even when Google's OIDC profile verifies the email.
    """
    from firebase_admin import auth
    claims = auth.verify_id_token(result['idToken'], app=admin_app(), check_revoked=True)
    if claims.get('email_verified') is True:
        return result['idToken']
    user = auth.get_user(claims['uid'], app=admin_app())
    email = str(profile.get('email', '')).strip().lower()
    matches = any(p.provider_id == 'google.com' and p.uid == profile.get('sub') for p in user.provider_data)
    if (profile.get('email_verified') is not True or not profile.get('sub') or not matches
            or not email or email != str(claims.get('email', '')).lower()
            or email != str(user.email or '').lower()
            or claims.get('firebase', {}).get('sign_in_provider') != 'google.com'):
        raise HTTPException(403, detail={'code': 'email_verification_required',
            'message': 'Verify your email before signing in. Check your inbox or resend verification.'})
    auth.update_user(claims['uid'], email_verified=True, app=admin_app())
    # Refresh the signed token so session() still enforces email_verified itself.
    return api('refreshToken', {'refresh_token': result['refreshToken']})['id_token']
