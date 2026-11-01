"""Google Sign-In: OAuth2 login, a signed session cookie, and the middleware
that gates the /v1 API behind it once Google credentials are configured.

No persistent user store — this stays the single-tenant prototype described in
docs/DATA_MODEL.md (``users``/``auth_identities`` are explicitly deferred there).
A successful Google sign-in just stores the profile Google returns in the
session cookie; every route still serves the one shared workspace.
"""

from __future__ import annotations

import os
import secrets

from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse

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
        "process, so signed-in sessions will not survive a restart. Set SESSION_SECRET "
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

# The Docker healthcheck (compose.yaml) hits this without a session.
_PUBLIC_API_PATHS = {"/v1/healthz"}


class AuthGateMiddleware(BaseHTTPMiddleware):
    """Requires a signed-in session for /v1/* once Google OAuth is configured.

    Left open when OAUTH_CONFIGURED is false so local dev and the backend test
    suite — neither of which sets GOOGLE_CLIENT_ID — keep working exactly as
    before. Setting up sign-in is what turns the gate on, not a separate flag.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if OAUTH_CONFIGURED and path.startswith("/v1") and path not in _PUBLIC_API_PATHS:
            if not request.session.get("user"):
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"error": {"code": "not_authenticated", "message": "Sign in required."}},
                )
        return await call_next(request)


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
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as error:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "google_auth_failed", "message": str(error)},
        ) from error
    userinfo = token.get("userinfo") or {}
    if not userinfo.get("email"):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "google_auth_failed", "message": "Google did not return an account email."},
        )
    request.session["user"] = {
        "email": userinfo["email"],
        "name": userinfo.get("name") or userinfo["email"],
        "picture": userinfo.get("picture"),
    }
    # Relative redirect: resolves against whatever origin the browser is
    # actually on (Vite at :5173, or Caddy at :8080), so no frontend URL
    # needs to be configured here.
    return RedirectResponse(url="/")


@router.get("/me")
def me(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "not_authenticated", "message": "Not signed in."})
    return {"data": user}


@router.post("/logout")
def logout(request: Request):
    request.session.pop("user", None)
    return {"data": {"ok": True}}
