"""FastAPI-Dependencies für Authentifizierung und Rollen."""

from __future__ import annotations

from fastapi import HTTPException, Request

from . import config, security


def token_from_request(request: Request) -> str | None:
    """Session-Token: primär HttpOnly-Cookie, Fallback Authorization: Bearer.

    Der Bearer-Fallback macht die Anmeldung unabhängig von Browser-Cookie-
    Einstellungen; das Frontend hält das Token nur im Speicher."""
    token = request.cookies.get(config.SESSION_COOKIE)
    if token:
        return token
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def current_user(request: Request) -> dict:
    session = security.get_session(token_from_request(request))
    if not session:
        raise HTTPException(401, "Nicht angemeldet")
    return session


def admin_required(request: Request) -> dict:
    session = current_user(request)
    if session["role"] != "admin":
        raise HTTPException(403, "Nur für Administratoren")
    return session
