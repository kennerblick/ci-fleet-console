"""Standard-Vorlagen aus dem ci-templates-Projekt (Ordner standard/<Kategorie>)."""

from __future__ import annotations

import re

import gitlab
from fastapi import HTTPException

from .. import cache, config, settings_store
from ..gitlab_client import gl

_CATEGORY_RE = re.compile(r"^[A-Za-z0-9._ -]+$")


def _project():
    s = settings_store.current()
    path = ((s.get("templates_project") or "").strip("/")
            or f"{s['group_path'].rstrip('/')}/ci-templates")
    try:
        return gl().projects.get(path)
    except gitlab.exceptions.GitlabGetError:
        raise HTTPException(404, f"Template-Projekt {path} nicht gefunden")


def _dir() -> str:
    return ((settings_store.current().get("templates_dir")
             or config.DEFAULT_TEMPLATES_DIR).strip("/"))


def categories(refresh: bool = False) -> dict:
    if not refresh:
        cached = cache.get("templates", config.TTL_TEMPLATES)
        if cached:
            return cached
    proj = _project()
    tree = proj.repository_tree(path=_dir(), ref=proj.default_branch,
                                per_page=100, get_all=True)
    return cache.put("templates", {
        "categories": sorted(t["name"] for t in tree if t["type"] == "tree")})


def content(category: str) -> dict:
    """YAML-Vorlage einer Kategorie (bevorzugt .gitlab-ci.yml im Ordner)."""
    if not _CATEGORY_RE.fullmatch(category):
        raise HTTPException(400, "Ungültige Kategorie")
    proj = _project()
    ref = proj.default_branch
    try:
        files = proj.repository_tree(path=f"{_dir()}/{category}", ref=ref,
                                     per_page=100, get_all=True)
    except gitlab.exceptions.GitlabGetError:
        raise HTTPException(404, f"Kategorie {category} nicht gefunden")
    ymls = [f for f in files if f["type"] == "blob"
            and f["name"].lower().endswith((".yml", ".yaml"))]
    pick = next((f for f in ymls if f["name"] in (config.CI_FILE, "gitlab-ci.yml")),
                ymls[0] if ymls else None)
    if not pick:
        raise HTTPException(404, f"Keine YAML-Datei in {_dir()}/{category}")
    f = proj.files.get(pick["path"], ref=ref)
    return {"category": category, "file": pick["path"],
            "content": f.decode().decode("utf-8")}
