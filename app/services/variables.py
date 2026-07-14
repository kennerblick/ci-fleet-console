"""CI-VARS-Prüfung gegen Projekt-/Gruppen-Variablen und Anlegen fehlender."""

from __future__ import annotations

import re

import gitlab

from .. import cache, config
from ..ci_vars import VAR_NAME_RE, parse_required_vars
from ..gitlab_client import gl
from .pipelines import get_project

_SECRET_RE = re.compile(r"(PASSWORD|PASSPHRASE|SECRET|TOKEN|_KEY)", re.I)


def _group_var_keys(group_path: str) -> list[str]:
    key = f"groupvars_{group_path}"
    cached = cache.get(key, config.TTL_GROUP_VARS)
    if cached is not None:
        return cached
    try:
        group = gl().groups.get(group_path)
        keys = [v.key for v in group.variables.list(get_all=True)]
    except Exception:
        keys = []
    return cache.put(key, keys)


def status(project_id: int, content: str) -> dict:
    """Deklarierte Variablen gegen Projekt- und geerbte Gruppen-Variablen prüfen.
    Werte werden nie ausgelesen, nur die Existenz."""
    proj = get_project(project_id)
    required = parse_required_vars(content)
    if not required:
        return {"declared": False, "required": [], "can_manage": True,
                "missing_required": []}

    available: dict[str, str] = {}
    can_manage = True
    try:
        for v in proj.variables.list(get_all=True):
            available[v.key] = "Projekt"
    except Exception:
        can_manage = False          # Variablen-API braucht Maintainer-Rolle

    parts = proj.path_with_namespace.split("/")[:-1]
    for i in range(1, len(parts) + 1):
        group_path = "/".join(parts[:i])
        for key in _group_var_keys(group_path):
            available.setdefault(key, f"Gruppe {group_path}")

    for entry in required:
        entry["present"] = entry["name"] in available
        entry["source"] = available.get(entry["name"])
    missing = [e["name"] for e in required
               if not e["present"] and e.get("default") is None]
    return {"declared": True, "required": required,
            "can_manage": can_manage, "missing_required": missing}


def save(project_id: int, variables: list[dict]) -> list[dict]:
    """Fehlende Variablen als Projekt-Variablen anlegen bzw. aktualisieren."""
    proj = get_project(project_id)
    results = []
    for item in variables:
        key = (item.get("key") or "").strip()
        value = item.get("value")
        if not VAR_NAME_RE.match(key) or value in (None, ""):
            continue
        try:
            try:
                var = proj.variables.get(key)
                var.value = value
                var.save()
                results.append({"key": key, "action": "aktualisiert"})
            except gitlab.exceptions.GitlabGetError:
                payload = {"key": key, "value": value, "protected": False}
                if _SECRET_RE.search(key):
                    try:            # masked hat Format-Anforderungen
                        proj.variables.create({**payload, "masked": True})
                        results.append({"key": key, "action": "erstellt (masked)"})
                        continue
                    except gitlab.exceptions.GitlabCreateError:
                        pass
                proj.variables.create(payload)
                results.append({"key": key, "action": "erstellt"})
        except gitlab.exceptions.GitlabError as e:
            results.append({"key": key, "action": "FEHLER",
                            "detail": str(getattr(e, "error_message", e))})
    return results
