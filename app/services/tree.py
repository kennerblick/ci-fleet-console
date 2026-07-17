"""Projektbaum der konfigurierten Gruppe inkl. CI-Status je Projekt."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import gitlab
from fastapi import HTTPException

from .. import cache, config, settings_store
from ..gitlab_client import ctx_submit, gl
from .pipelines import pipeline_dict

log = logging.getLogger("cifc.tree")


def _enrich(project: dict) -> dict:
    """CI-Datei vorhanden? + letzte Pipelines (Sparkline, ohne skipped)."""
    proj = gl().projects.get(project["id"], lazy=True)
    ref = project.get("default_branch") or "main"

    try:
        proj.files.head(config.CI_FILE, ref=ref)
        project["has_ci"] = True
    except Exception:
        project["has_ci"] = False

    pipes: list[dict] = []
    try:
        raw = proj.pipelines.list(ref=ref, per_page=config.SPARK_COUNT * 4, page=1)
        pipes = [pipeline_dict(p) for p in raw
                 if p.attributes.get("status") != "skipped"][:config.SPARK_COUNT]
    except Exception:
        log.debug("Pipelines für %s nicht lesbar", project["full_path"])
    project["pipelines"] = pipes
    return project


def build(refresh: bool = False) -> dict:
    """Stale-While-Revalidate: abgelaufene Daten sofort liefern und den
    teuren Neuaufbau (2 GitLab-Calls je Projekt) im Hintergrund erledigen."""
    if not refresh:
        cached, fresh = cache.get_with_stale("tree", config.TTL_TREE)
        if cached and fresh:
            cached["cached"] = True
            cached["stale"] = False
            return cached
        if cached:
            cache.refresh_in_background("tree", _rebuild)
            cached["cached"] = True
            cached["stale"] = True
            return cached
    return _rebuild()


def _rebuild() -> dict:
    settings = settings_store.current()
    group_path = settings["group_path"]
    try:
        group = gl().groups.get(group_path)
    except gitlab.exceptions.GitlabGetError:
        raise HTTPException(404, f"Gruppe {group_path} nicht gefunden")

    prefix = group_path.rstrip("/") + "/"
    projects = []
    for raw in group.projects.list(include_subgroups=True, archived=False,
                                   iterator=True, per_page=100):
        a = raw.attributes
        full = a.get("path_with_namespace", "")
        projects.append({
            "id": a.get("id"),
            "name": a.get("name"),
            "full_path": full,
            "rel_path": full[len(prefix):] if full.startswith(prefix) else full,
            "default_branch": a.get("default_branch"),
            "web_url": a.get("web_url"),
            "last_activity_at": a.get("last_activity_at"),
        })

    selected = settings.get("selected_groups") or []
    if selected:
        def keep(rel: str) -> bool:
            if "/" not in rel:                  # Projekt direkt in der Wurzel
                return "." in selected
            return rel.split("/")[0] in selected
        projects = [p for p in projects if keep(p["rel_path"])]

    with ThreadPoolExecutor(max_workers=config.WORKERS) as ex:
        futures = [ctx_submit(ex, _enrich, p) for p in projects]
        projects = [f.result() for f in as_completed(futures)]

    projects.sort(key=lambda p: p["rel_path"].lower())
    return cache.put("tree", {
        "group": group_path,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "projects": projects,
        "cached": False,
        "stale": False,
    })
