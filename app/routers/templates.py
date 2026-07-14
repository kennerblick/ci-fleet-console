"""Standard-Vorlagen (Kategorien und Inhalte)."""

from __future__ import annotations

from fastapi import APIRouter

from ..services import templates

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("")
def list_categories(refresh: int = 0):
    return templates.categories(refresh=bool(refresh))


@router.get("/{category}")
def get_template(category: str):
    return templates.content(category)
