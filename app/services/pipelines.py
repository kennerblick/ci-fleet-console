"""Pipelines, Jobs (inkl. Trigger-Bridges und Child-Pipelines), Job-Aktionen."""

from __future__ import annotations

import gitlab
from fastapi import HTTPException

from .. import cache, config
from ..gitlab_client import gl

JOB_ACTIONS = ("play", "retry", "cancel")


def get_project(project_id: int):
    try:
        return gl().projects.get(project_id)
    except gitlab.exceptions.GitlabGetError:
        raise HTTPException(404, "Projekt nicht gefunden")


def pipeline_dict(p) -> dict:
    a = p.attributes
    return {
        "id": a.get("id"), "status": a.get("status"), "ref": a.get("ref"),
        "sha": (a.get("sha") or "")[:8], "source": a.get("source"),
        "created_at": a.get("created_at"), "updated_at": a.get("updated_at"),
        "web_url": a.get("web_url"),
    }


def _job_dict(j, bridge: bool = False) -> dict:
    a = j.attributes
    return {
        "id": a.get("id"), "name": a.get("name"), "stage": a.get("stage"),
        "status": a.get("status"), "duration": a.get("duration"),
        "web_url": a.get("web_url"), "bridge": bridge, "downstream": None,
    }


def list_pipelines(project_id: int, refresh: bool = False,
                   per_page: int = 20) -> dict:
    key = f"pipelines_{project_id}"
    if not refresh:
        cached = cache.get(key, config.TTL_PIPELINES)
        if cached:
            return cached
    proj = get_project(project_id)
    raw = proj.pipelines.list(per_page=min(per_page * 3, 100), page=1)
    pipes = [pipeline_dict(p) for p in raw
             if p.attributes.get("status") != "skipped"][:per_page]
    return cache.put(key, {"pipelines": pipes})


def pipeline_jobs(project_id: int, pipeline_id: int, depth: int = 0) -> list[dict]:
    """Jobs + Trigger-Bridges einer Pipeline; Child-Pipelines bis Tiefe 2."""
    proj = gl().projects.get(project_id, lazy=True)
    pipe = proj.pipelines.get(pipeline_id)
    entries = [_job_dict(j) for j in pipe.jobs.list(per_page=100, get_all=True)]

    for bridge in pipe.bridges.list(per_page=100, get_all=True):
        entry = _job_dict(bridge, bridge=True)
        down = bridge.attributes.get("downstream_pipeline")
        if down:
            entry["downstream"] = {
                "id": down.get("id"), "status": down.get("status"),
                "web_url": down.get("web_url"),
                "jobs": (pipeline_jobs(down.get("project_id", project_id),
                                       down["id"], depth + 1)
                         if depth < 2 else []),
            }
        entries.append(entry)

    entries.sort(key=lambda j: j["id"])         # Ausführungsreihenfolge
    return entries


def flatten_jobs(entries: list[dict], prefix: str = "") -> list[dict]:
    """Jobs inkl. Child-Pipeline-Jobs flach ('Configs ▸ collect-configs')."""
    flat: list[dict] = []
    for job in entries:
        qname = prefix + job["name"]
        flat.append({**job, "qname": qname})
        if job.get("bridge") and job.get("downstream"):
            flat.extend(flatten_jobs(job["downstream"].get("jobs") or [],
                                     prefix=qname + " ▸ "))
    return flat


def latest_pipeline(project_id: int) -> dict | None:
    """Neueste nicht übersprungene Pipeline eines Projekts (oder None)."""
    proj = get_project(project_id)
    for p in proj.pipelines.list(per_page=10, page=1):
        if p.attributes.get("status") != "skipped":
            return pipeline_dict(p)
    return None


def run_pipeline(project_id: int, ref: str | None,
                 variables: list[dict]) -> dict:
    proj = get_project(project_id)
    payload: dict = {"ref": ref or proj.default_branch}
    clean = [{"key": v["key"], "value": v["value"]}
             for v in variables if isinstance(v, dict) and v.get("key")]
    if clean:
        payload["variables"] = clean
    try:
        pipe = proj.pipelines.create(payload)
    except gitlab.exceptions.GitlabCreateError as e:
        raise HTTPException(400, f"Pipeline konnte nicht gestartet werden: {e.error_message}")
    cache.invalidate(f"pipelines_{project_id}")
    return pipeline_dict(pipe)


def job_action(project_id: int, job_id: int, action: str) -> None:
    if action not in JOB_ACTIONS:
        raise HTTPException(400, f"Unbekannte Aktion: {action}")
    proj = get_project(project_id)
    try:
        job = proj.jobs.get(job_id, lazy=True)
        getattr(job, action)()
    except gitlab.exceptions.GitlabError as e:
        raise HTTPException(400, f"Aktion fehlgeschlagen: {getattr(e, 'error_message', e)}")
    cache.invalidate(f"pipelines_{project_id}")
