"""Login, Logout, Session-Info."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .. import ad, config, security
from ..deps import token_from_request
from ..schemas import LoginBody

log = logging.getLogger("cifc.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(request: Request, body: LoginBody):
    username, password = body.username.strip(), body.password
    key = security.rate_key(request.client.host if request.client else "?", username)
    if security.rate_blocked(key):
        raise HTTPException(429, "Zu viele Fehlversuche – bitte 5 Minuten warten")

    user = None
    local = security.find_local_user(username)
    if local and security.verify_password(password, local["salt"], local["hash"]):
        user = {"user": local["username"], "role": local["role"], "source": "local"}
    if not user:
        result = ad.authenticate(username, password)
        if result:
            user = {"user": username, "role": result["role"], "source": "ad"}
    if not user:
        security.rate_fail(key)
        log.info("Login fehlgeschlagen: %s", username)
        raise HTTPException(401, "Anmeldung fehlgeschlagen")

    security.rate_reset(key)
    token = security.create_session(user["user"], user["role"], user["source"])
    log.info("Login: %s (%s, %s)", user["user"], user["role"], user["source"])
    # Token zusätzlich im Body: Fallback für Browser, die das Cookie
    # nicht speichern/senden (Frontend hält es nur im Speicher).
    response = JSONResponse({"username": user["user"], "role": user["role"],
                             "source": user["source"], "token": token})
    response.set_cookie(config.SESSION_COOKIE, token, httponly=True,
                        samesite="lax", secure=config.SESSION_SECURE,
                        max_age=config.SESSION_TTL, path="/")
    return response


@router.post("/logout")
def logout(request: Request):
    security.drop_session(request.cookies.get(config.SESSION_COOKIE))
    response = JSONResponse({"ok": True})
    response.delete_cookie(config.SESSION_COOKIE, path="/")
    return response


@router.get("/me")
def me(request: Request):
    session = security.get_session(token_from_request(request))
    if not session:
        raise HTTPException(401, "Nicht angemeldet")
    return {"username": session["user"], "role": session["role"],
            "source": session["source"]}
