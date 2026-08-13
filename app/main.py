"""App-Factory: Middleware, Router, Logging.

Start:  uvicorn app.main:app --host 0.0.0.0 --port 8090
"""

from __future__ import annotations

import logging
import time

import gitlab
from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, security, settings_store
from .routers import (auth, groups, maintenance, projects, settings, system,
                      templates, users)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

log = logging.getLogger("cifc")
SLOW_REQUEST_SECONDS = 1.0

_PUBLIC_PREFIXES = ("/api/auth/",)


def create_app() -> FastAPI:
    security.bootstrap_admin()
    application = FastAPI(title="CI Fleet Console", docs_url=None, redoc_url=None)
    application.add_middleware(GZipMiddleware, minimum_size=1024)

    @application.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and not path.startswith(_PUBLIC_PREFIXES):
            from .deps import token_from_request
            session = security.get_session(token_from_request(request))
            if not session:
                has_cookie = config.SESSION_COOKIE in request.headers.get("cookie", "")
                log.info("401 %s %s – Session-Cookie im Request: %s",
                         request.method, path,
                         "ja (Session unbekannt/abgelaufen)" if has_cookie else "NEIN")
                return JSONResponse(status_code=401,
                                    content={"detail": "Nicht angemeldet"})
            request.state.user = session
            settings_store.set_context(session["user"])
        started = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - started
        if elapsed > SLOW_REQUEST_SECONDS and path.startswith("/api/"):
            log.warning("Langsamer Request %.2fs: %s %s",
                        elapsed, request.method, path)
        return response

    @application.exception_handler(gitlab.exceptions.GitlabAuthenticationError)
    async def gitlab_auth_error(request: Request, _):
        # WICHTIG: 400, nicht 401 - ein von GitLab abgelehntes PAT ist kein
        # Session-Problem; 401 wuerde das Frontend faelschlich ausloggen.
        log.warning("GitLab hat das konfigurierte Token abgelehnt (%s %s)",
                    request.method, request.url.path)
        return JSONResponse(status_code=400, content={
            "detail": "GitLab-Token ungültig oder abgelaufen – bitte in "
                      "⚙ Konfiguration ein gültiges Token (Scope: api) hinterlegen"})

    for router in (auth.router, users.router, settings.router, projects.router,
                   templates.router, groups.router, system.router,
                   maintenance.router):
        application.include_router(router)

    application.mount("/static", StaticFiles(directory=config.STATIC_DIR),
                      name="static")
    return application


app = create_app()
