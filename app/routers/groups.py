"""Gruppen-Job-Matrix."""

from __future__ import annotations

from fastapi import APIRouter

from ..services import group_matrix

router = APIRouter(prefix="/api/groups", tags=["groups"])


@router.get("/jobs")
def group_jobs(path: str = "", refresh: int = 0):
    return group_matrix.build(path, refresh=bool(refresh))
