"""Shared cookie policy for local and managed authentication."""
import os


def set_session_cookie(response, request, name, token, max_age):
    response.set_cookie(name, token, max_age=max_age, httponly=True, samesite='lax',
                        secure=request.url.scheme == 'https' or os.getenv('SESSION_COOKIE_SECURE', '').lower() == 'true')
    return response
