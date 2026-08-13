"""Wartungsmodus: Tagging (Bulk-Update/Bulk-Reboot je Servergruppe) und
Bulk-Trigger über den bestehenden Einzelprojekt-Pipeline-Trigger."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException

from .. import config, maintenance_store
from ..gitlab_client import ctx_submit
from . import pipelines, tree


def list_tags() -> dict:
    return maintenance_store.get_all()


def set_tag(project_id: int, update: bool, reboot: bool,
           server_group: str | None) -> dict | None:
    return maintenance_store.set_tag(project_id, update, reboot, server_group)


def _project_names() -> dict[str, str]:
    tree_data = tree.build()
    return {str(p["id"]): p["name"] for p in tree_data["projects"]}


def _trigger(args: tuple[int, str | None, list[dict]]) -> tuple[int, dict | None, str | None]:
    project_id, ref, variables = args
    try:
        pipe = pipelines.run_pipeline(project_id, ref, variables)
        return project_id, pipe, None
    except HTTPException as e:
        return project_id, None, str(e.detail)


def bulk_run(action: str, server_group: str, variables: list[dict]) -> dict:
    if action not in ("update", "reboot"):
        raise HTTPException(400, f"Unbekannte Aktion: {action}")

    tags = maintenance_store.get_all()
    project_ids = [int(pid) for pid, tag in tags.items()
                   if tag.get("server_group") == server_group and tag.get(action)]
    if not project_ids:
        raise HTTPException(404, f"Keine Projekte für {server_group}/{action} getaggt")

    names = _project_names()
    jobs = [(pid, None, variables) for pid in project_ids]
    with ThreadPoolExecutor(max_workers=config.WORKERS) as ex:
        results = [f.result() for f in
                   [ctx_submit(ex, _trigger, job) for job in jobs]]

    triggered = [{"project_id": pid, "name": names.get(str(pid), str(pid)),
                 "pipeline": pipe}
                for (pid, pipe, err) in results if pipe]
    failed = [{"project_id": pid, "name": names.get(str(pid), str(pid)), "error": err}
             for (pid, pipe, err) in results if err]

    return {"action": action, "server_group": server_group, "total": len(project_ids),
            "triggered": triggered, "failed": failed}
