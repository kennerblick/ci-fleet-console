"""Startseite und Cache-Verwaltung."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from .. import cache, config

router = APIRouter(tags=["system"])


@router.get("/", include_in_schema=False)
def index():
    # index.html nie cachen: sie referenziert die Assets mit Versionsparameter,
    # damit Browser nach Updates garantiert das neue JS/CSS laden.
    return FileResponse(config.STATIC_DIR / "index.html",
                        headers={"Cache-Control": "no-cache"})


@router.get("/api/cache/info")
def cache_info():
    return cache.info()


@router.post("/api/cache/clear")
def cache_clear():
    return {"ok": True, "deleted": cache.clear_all()}
