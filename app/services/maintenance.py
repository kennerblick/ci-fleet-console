"""Wartungsmodus: Tagging (Update/Reboot je Servergruppe) und Bulk-Aktionen.

Bulk-Aktionen spielen die passenden, bereits in der jeweils letzten Pipeline
vorhandenen Wartungs-Jobs ab (linux-gitlab-ci.yml -> linux-wartung.yml bzw.
microsoft-gitlab-ci.yml -> microsoft-update.yml) - kein neuer Pipeline-Lauf,
sondern derselbe Mechanismus wie der bestehende ▶-Play-Button auf einem Job.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException

from .. import config, maintenance_store
from ..gitlab_client import ctx_submit
from . import pipelines, tree

# Job-Namen je Betriebssystem-Familie und Aktion. linux-intern und
# linux-extern verwenden dieselben Jobs aus linux-wartung.yml.
JOB_NAMES = {
    ("linux", "update"): ["apt-update", "apt-upgrade"],
    ("linux", "reboot"): ["system-reboot"],
    ("linux", "cron-stop"): ["cron-stop"],
    ("windows", "update"): ["windows-updates-install"],
    ("windows", "reboot"): ["windows-reboot"],
}


def _os_family(server_group: str) -> str:
    return "windows" if server_group == "windows" else "linux"


def list_tags() -> dict:
    return maintenance_store.get_all()


def set_tag(project_id: int, update: bool, reboot: bool,
           server_group: str | None) -> dict | None:
    return maintenance_store.set_tag(project_id, update, reboot, server_group)


def _project_names() -> dict[str, str]:
    tree_data = tree.build()
    return {str(p["id"]): p["name"] for p in tree_data["projects"]}


def _jobs_by_name(project_id: int, pipeline_id: int) -> dict[str, dict]:
    """Jobs der Pipeline inkl. aller Kind-Pipelines hinter Trigger-Bridges,
    flach nach einfachem Job-Namen (nicht qname) indiziert."""
    flat = pipelines.flatten_jobs(pipelines.pipeline_jobs(project_id, pipeline_id))
    return {j["name"]: j for j in flat}


def _play_jobs(project_id: int, job_names: list[str]) -> list[str]:
    """Spielt die angegebenen Jobs der letzten Pipeline ab, liefert die
    tatsächlich gespielten Namen oder wirft HTTPException, wenn keine
    Pipeline existiert oder ein Job dort fehlt.

    apt-update/apt-upgrade/cron-stop liegen nicht auf oberster Ebene, sondern
    in der Kind-Pipeline hinter dem manuellen Trigger-Job MAINT_BRIDGE_NAME
    ("Wartung") - der wird bei Bedarf zuerst gespielt, danach wird auf das
    Erscheinen der Kind-Pipeline-Jobs gewartet."""
    pipe = pipelines.latest_pipeline(project_id)
    if not pipe:
        raise HTTPException(404, "Keine Pipeline vorhanden")

    by_name = _jobs_by_name(project_id, pipe["id"])
    missing = [name for name in job_names if name not in by_name]

    if missing:
        bridge = by_name.get(config.MAINT_BRIDGE_NAME)
        if not bridge:
            raise HTTPException(
                404, f"Job(s) nicht in letzter Pipeline (#{pipe['id']}) gefunden: "
                     f"{', '.join(missing)}")
        if bridge["status"] == "manual":
            pipelines.job_action(project_id, bridge["id"], "play")
        for _ in range(config.MAINT_BRIDGE_POLL_ATTEMPTS):
            time.sleep(config.MAINT_BRIDGE_POLL_INTERVAL)
            by_name = _jobs_by_name(project_id, pipe["id"])
            missing = [name for name in job_names if name not in by_name]
            if not missing:
                break
        if missing:
            raise HTTPException(
                404, f"Job(s) auch nach Start von '{config.MAINT_BRIDGE_NAME}' nicht "
                     f"gefunden (Kind-Pipeline evtl. noch nicht fertig): {', '.join(missing)}")

    for name in job_names:
        pipelines.job_action(project_id, by_name[name]["id"], "play")
    return list(job_names)


def _trigger(args: tuple[int, list[str]]) -> tuple[int, list[str] | None, str | None]:
    project_id, job_names = args
    try:
        played = _play_jobs(project_id, job_names)
        return project_id, played, None
    except HTTPException as e:
        return project_id, None, str(e.detail)


def bulk_run(action: str, server_group: str) -> dict:
    family = _os_family(server_group)
    if (family, action) not in JOB_NAMES:
        raise HTTPException(400, f"{action} gibt es für {server_group} nicht")

    # cron-stop betrifft dieselbe Zielmenge wie update (Vorbereitung vor der
    # eigentlichen Wartung); reboot nur die dafür getaggte Teilmenge.
    tag_field = "reboot" if action == "reboot" else "update"

    tags = maintenance_store.get_all()
    project_ids = [int(pid) for pid, tag in tags.items()
                   if tag.get("server_group") == server_group and tag.get(tag_field)]
    if not project_ids:
        raise HTTPException(404, f"Keine Projekte für {server_group}/{action} getaggt")

    names = _project_names()
    job_names = JOB_NAMES[(family, action)]
    with ThreadPoolExecutor(max_workers=config.WORKERS) as ex:
        results = [f.result() for f in
                   [ctx_submit(ex, _trigger, (pid, job_names)) for pid in project_ids]]

    triggered = [{"project_id": pid, "name": names.get(str(pid), str(pid)), "jobs": played}
                for (pid, played, err) in results if err is None]
    failed = [{"project_id": pid, "name": names.get(str(pid), str(pid)), "error": err}
             for (pid, played, err) in results if err]

    return {"action": action, "server_group": server_group, "total": len(project_ids),
            "triggered": triggered, "failed": failed}
