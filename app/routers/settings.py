"""Konfiguration: pro Benutzer, Admin kann den Standard pflegen; Gruppen-Scan."""

from __future__ import annotations

import gitlab
from fastapi import APIRouter, Depends, HTTPException

from .. import cache, config, settings_store
from ..deps import current_user
from ..schemas import ScanBody, SettingsBody

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _view(session: dict) -> dict:
    e = settings_store.effective(session["user"])
    return {
        "gitlab_url": e["gitlab_url"],
        "group_path": e["group_path"],
        "selected_groups": e.get("selected_groups") or [],
        "templates_project": e.get("templates_project") or "",
        "templates_dir": e.get("templates_dir") or config.DEFAULT_TEMPLATES_DIR,
        "token_set": e["_own_token"],
        "default_token_set": settings_store.default_token_set(),
        "is_admin": session["role"] == "admin",
    }


@router.get("")
def get_settings(session: dict = Depends(current_user)):
    return _view(session)


@router.post("")
def save_settings(body: SettingsBody, session: dict = Depends(current_user)):
    as_default = body.as_default and session["role"] == "admin"
    settings_store.update(session["user"], body.model_dump(), as_default=as_default)
    cache.clear_all()
    settings_store.set_context(session["user"])
    return _view(session)


@router.post("/scan")
def scan(body: ScanBody, session: dict = Depends(current_user)):
    """Verzeichnisse (Subgruppen 1. Ebene) einlesen – testet zugleich die Verbindung."""
    e = settings_store.current()
    url = (body.gitlab_url or e["gitlab_url"]).strip()
    token = body.token or e["private_token"]
    group_path = (body.group_path or e["group_path"]).strip().strip("/")
    if not url or not token or not group_path:
        raise HTTPException(400, "GitLab-Adresse, Token und Gruppenpfad angeben")
    try:
        client = gitlab.Gitlab(url, private_token=token,
                               timeout=config.GITLAB_TIMEOUT)
        client.auth()
        group = client.groups.get(group_path)
        subs = group.subgroups.list(per_page=100, get_all=True)
        root_projects = group.projects.list(include_subgroups=False,
                                            archived=False, per_page=1)
    except gitlab.exceptions.GitlabAuthenticationError:
        raise HTTPException(401, "Token ungültig")
    except gitlab.exceptions.GitlabGetError:
        raise HTTPException(404, f"Gruppe {group_path} nicht gefunden")
    except Exception as e:
        raise HTTPException(400, f"Verbindung fehlgeschlagen: {e}")
    return {
        "user": client.user.username,
        "group_path": group_path,
        "directories": sorted(({"path": s.path, "name": s.name} for s in subs),
                              key=lambda d: d["path"].lower()),
        "has_root_projects": len(root_projects) > 0,
    }
