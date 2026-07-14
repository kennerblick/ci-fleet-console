"""Lesen, Versionieren und Committen der .gitlab-ci.yml."""

from __future__ import annotations

import gitlab
from fastapi import HTTPException

from .. import cache, config
from .pipelines import get_project


def read(project_id: int, ref: str | None = None) -> dict:
    proj = get_project(project_id)
    ref = ref or proj.default_branch
    try:
        f = proj.files.get(config.CI_FILE, ref=ref)
        return {"content": f.decode().decode("utf-8"), "ref": ref,
                "exists": True, "default_branch": proj.default_branch}
    except gitlab.exceptions.GitlabGetError:
        return {"content": "", "ref": ref, "exists": False,
                "default_branch": proj.default_branch}


def head_content(project_id: int) -> str | None:
    result = read(project_id)
    return result["content"] if result["exists"] else None


def versions(project_id: int, refresh: bool = False) -> dict:
    key = f"versions_{project_id}"
    if not refresh:
        cached = cache.get(key, config.TTL_VERSIONS)
        if cached:
            return cached
    proj = get_project(project_id)
    commits = proj.commits.list(path=config.CI_FILE,
                                ref_name=proj.default_branch, per_page=25)
    return cache.put(key, {
        "versions": [{"sha": c.id, "short": c.short_id, "title": c.title,
                      "author": c.author_name, "created_at": c.created_at}
                     for c in commits],
        "default_branch": proj.default_branch,
    })


def save(project_id: int, content: str, branch: str | None,
         message: str | None) -> dict:
    proj = get_project(project_id)
    branch = branch or proj.default_branch
    message = message or f"Update {config.CI_FILE} via CI Fleet Console"
    try:
        try:
            f = proj.files.get(config.CI_FILE, ref=branch)
            f.content = content
            f.save(branch=branch, commit_message=message)
            action = "aktualisiert"
        except gitlab.exceptions.GitlabGetError:
            proj.files.create({"file_path": config.CI_FILE, "branch": branch,
                               "content": content, "commit_message": message})
            action = "erstellt"
    except gitlab.exceptions.GitlabError as e:
        raise HTTPException(400, f"Commit fehlgeschlagen: {getattr(e, 'error_message', e)}")
    cache.invalidate(f"versions_{project_id}")
    return {"ok": True, "action": action, "branch": branch}
