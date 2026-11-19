"""Google OAuth establishes the same durable account session as password login.
The signed Starlette session is used only for the OAuth state/nonce handshake.
"""

from __future__ import annotations

import os
import secrets

from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request, status
from starlette.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool
from backend.db import postgres_enabled
from backend.accounts import accounts, COOKIE, public, session_response, uid, password_hash, validated_email

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
# Must exactly match an "Authorized redirect URI" on the Google OAuth client.
# Defaults to the Vite dev origin (npm run dev -- --port 5173), which proxies
# /auth/* to this backend the same way it already proxies /v1 (vite.config.ts)
# so the session cookie is set on one origin. Override for the Docker Compose
# flow (compose.yaml sets it to the Caddy origin, http://localhost:8080/...).
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:5173/auth/google/callback")
OAUTH_CONFIGURED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

SESSION_SECRET = os.getenv("SESSION_SECRET") or secrets.token_urlsafe(32)
if not os.getenv("SESSION_SECRET"):
    print(
        "WARNING: SESSION_SECRET is not set — using a random key generated for this "
        "process, so pending OAuth handshakes will not survive a restart. Set SESSION_SECRET "
        "in .env for stable sessions."
    )

oauth = OAuth()
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/config")
def config():
    return {"data": {"googleEnabled": OAUTH_CONFIGURED}}


@router.get("/google/login")
async def google_login(request: Request):
    if not OAUTH_CONFIGURED:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "oauth_not_configured", "message": "GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET are not set."},
        )
    return await oauth.google.authorize_redirect(request, OAUTH_REDIRECT_URI)


@router.get("/google/callback")
async def google_callback(request: Request):
    if not OAUTH_CONFIGURED:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google sign-in is not configured.")
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as error:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "google_auth_failed", "message": str(error)},
        ) from error
    userinfo = token.get("userinfo") or {}
    if not userinfo.get("sub") or not userinfo.get("email") or userinfo.get("email_verified") is not True:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Google did not return a verified account email and subject.")
    return await run_in_threadpool(google_session, request, userinfo)


def google_session(request, userinfo):
    email = validated_email(userinfo["email"])
    signed_in = accounts.user_for_token(request.cookies.get(COOKIE))
    with accounts.transaction() as sql:
        if postgres_enabled():
            sql("LOCK TABLE app_users IN EXCLUSIVE MODE")
        # Provider subject is stable even when the Google profile email changes.
        row = sql("SELECT u.* FROM app_users u JOIN google_identities g ON g.user_id=u.id WHERE g.subject=%s", (userinfo["sub"],)).fetchone()
        if row is None:
            row = sql("SELECT * FROM app_users WHERE email=%s", (email,)).fetchone()
            if row is not None and (not signed_in or signed_in['id'] != row['id']):
                raise HTTPException(status.HTTP_409_CONFLICT,
                    detail="Sign in with your password first, then connect Google from account settings.")
            if row is None:
                row = {"id": uid(), "email": email, "name": (userinfo.get("name") or email)[:80],
                       "password_hash": password_hash(secrets.token_urlsafe(64))}
                sql("INSERT INTO app_users(id,email,name,password_hash) VALUES (%s,%s,%s,%s)",
                    (row["id"], row["email"], row["name"], row["password_hash"]))
            sql("INSERT INTO google_identities(subject,user_id) VALUES (%s,%s)", (userinfo["sub"], row["id"]))
        request.session.clear()
        return session_response(dict(row), request, sql, response=RedirectResponse(url="/"))


@router.get("/me")
def me(request: Request):
    user = accounts.user_for_token(request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not signed in.")
    return {"data": public(user)}


@router.post("/logout")
def logout(request: Request):
    # Keep the original OAuth URL as an alias with the same CSRF protection.
    origin = request.headers.get("origin")
    allowed = {str(request.base_url).rstrip("/"), "http://localhost:5173", "http://127.0.0.1:5173"}
    if (origin and origin not in allowed) or request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Cross-site requests are not allowed.")
    from backend.accounts import logout as account_logout
    request.session.clear()
    return account_logout(request)
