"""Gemeinsame Jobs aller Projekte einer (Unter-)Gruppe als Matrix."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException

from .. import cache, config
from ..gitlab_client import ctx_submit, gl
from . import tree
from .pipelines import flatten_jobs, pipeline_dict, pipeline_jobs


def _latest_and_jobs(project: dict):
    try:
        proj = gl().projects.get(project["id"], lazy=True)
        pipe = None
        for x in proj.pipelines.list(per_page=10, page=1):
            if x.attributes.get("status") != "skipped":
                pipe = pipeline_dict(x)
                break
        if not pipe:
            return project, None, []
        return project, pipe, flatten_jobs(pipeline_jobs(project["id"], pipe["id"]))
    except Exception:
        return project, None, []


def build(path: str, refresh: bool = False) -> dict:
    """Stale-While-Revalidate wie beim Projektbaum."""
    key = f"groupjobs_{path or '_root'}"
    if not refresh:
        cached, fresh = cache.get_with_stale(key, config.TTL_GROUP_JOBS)
        if cached and fresh:
            cached["stale"] = False
            return cached
        if cached:
            cache.refresh_in_background(key, lambda: _rebuild(path, key))
            cached["stale"] = True
            return cached
    return _rebuild(path, key)


def _rebuild(path: str, key: str) -> dict:
    tree_data = cache.get("tree", config.TTL_TREE) or tree.build()
    prefix = path.strip("/")
    projects = ([p for p in tree_data["projects"]
                 if p["rel_path"] == prefix or p["rel_path"].startswith(prefix + "/")]
                if prefix else list(tree_data["projects"]))
    if not projects:
        raise HTTPException(404, f"Keine Projekte unter {prefix or '/'}")

    with ThreadPoolExecutor(max_workers=config.WORKERS) as ex:
        results = [f.result() for f in
                   [ctx_submit(ex, _latest_and_jobs, p) for p in projects]]

    active = [(p, pipe, flat) for (p, pipe, flat) in results if pipe]
    excluded = sorted(p["name"] for (p, pipe, _) in results if not pipe)
    if not active:
        return cache.put(key, {"stale": False, "path": prefix, "projects": [],
                               "excluded": excluded, "jobs": []})

    common: set | None = None
    for (_, _, flat) in active:
        keys = {(f["stage"], f["qname"], f["bridge"]) for f in flat}
        common = keys if common is None else (common & keys)

    rows, seen = [], set()
    for f in active[0][2]:                      # Reihenfolge des ersten Projekts
        k = (f["stage"], f["qname"], f["bridge"])
        if k in common and k not in seen:
            seen.add(k)
            rows.append({"stage": f["stage"], "name": f["qname"],
                         "bridge": f["bridge"], "cells": {}})

    for (project, pipe, flat) in active:
        lookup: dict = {}
        for f in flat:
            lookup.setdefault((f["stage"], f["qname"], f["bridge"]), f)
        for row in rows:
            f = lookup.get((row["stage"], row["name"], row["bridge"]))
            if f:
                row["cells"][str(project["id"])] = {
                    "status": f["status"], "web_url": f["web_url"],
                    "job_id": f["id"], "duration": f["duration"],
                }

    return cache.put(key, {
        "stale": False,
        "path": prefix,
        "projects": [{"id": p["id"], "name": p["name"], "rel_path": p["rel_path"],
                      "pipeline": pipe} for (p, pipe, _) in active],
        "excluded": excluded,
        "jobs": rows,
    })
