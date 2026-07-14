"""Projektbaum, Pipelines/Jobs, CI-Datei, CI-VARS eines Projekts."""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas import CheckContentBody, RunPipelineBody, SaveCiBody, VarsSaveBody
from ..services import ci_file, pipelines, tree, variables

router = APIRouter(prefix="/api", tags=["projects"])


@router.get("/tree")
def get_tree(refresh: int = 0):
    return tree.build(refresh=bool(refresh))


@router.get("/projects/{project_id}/pipelines")
def list_pipelines(project_id: int, refresh: int = 0, per_page: int = 20):
    return pipelines.list_pipelines(project_id, refresh=bool(refresh),
                                    per_page=per_page)


@router.post("/projects/{project_id}/pipelines")
def run_pipeline(project_id: int, body: RunPipelineBody):
    return pipelines.run_pipeline(project_id, body.ref, body.variables)


@router.get("/projects/{project_id}/pipelines/{pipeline_id}/jobs")
def get_jobs(project_id: int, pipeline_id: int):
    pipelines.get_project(project_id)       # validiert Existenz/Rechte
    return {"jobs": pipelines.pipeline_jobs(project_id, pipeline_id)}


@router.post("/projects/{project_id}/jobs/{job_id}/{action}")
def job_action(project_id: int, job_id: int, action: str):
    pipelines.job_action(project_id, job_id, action)
    return {"ok": True, "action": action}


@router.get("/projects/{project_id}/ci")
def get_ci(project_id: int, ref: str | None = None):
    return ci_file.read(project_id, ref)


@router.put("/projects/{project_id}/ci")
def save_ci(project_id: int, body: SaveCiBody):
    return ci_file.save(project_id, body.content, body.branch, body.message)


@router.get("/projects/{project_id}/ci/versions")
def ci_versions(project_id: int, refresh: int = 0):
    return ci_file.versions(project_id, refresh=bool(refresh))


@router.get("/projects/{project_id}/vars/check")
def vars_check(project_id: int):
    content = ci_file.head_content(project_id)
    if content is None:
        return {"declared": False, "required": [], "can_manage": True,
                "missing_required": []}
    return variables.status(project_id, content)


@router.post("/projects/{project_id}/vars/check-content")
def vars_check_content(project_id: int, body: CheckContentBody):
    """Wie /vars/check, aber gegen noch nicht committeten Inhalt."""
    return variables.status(project_id, body.content)


@router.post("/projects/{project_id}/vars")
def vars_save(project_id: int, body: VarsSaveBody):
    return {"results": variables.save(project_id, body.variables)}
