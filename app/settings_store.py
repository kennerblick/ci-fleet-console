"""Einstellungen: Standard-Konfiguration plus persönliche Overrides je Benutzer.

Auflösung zur Laufzeit über eine ContextVar, die die Auth-Middleware pro
Request setzt – so sehen auch Service-Funktionen und Worker-Threads die
Konfiguration des anfragenden Benutzers, ohne sie durchreichen zu müssen.
"""

from __future__ import annotations

import contextvars
import hashlib
import threading
from typing import Any, Optional

from . import config
from .storage import load_json, write_private

_DEFAULT_KEYS = ("gitlab_url", "private_token", "group_path",
                 "selected_groups", "templates_project", "templates_dir")

_lock = threading.Lock()
_generation = 0
_ctx: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "cifc_settings", default=None)


def _base_default() -> dict:
    legacy = config.legacy_config()
    return {
        "gitlab_url": legacy["gitlab_url"],
        "private_token": legacy["private_token"],
        "group_path": legacy["group_path"],
        "selected_groups": [],                  # leer = alle Verzeichnisse
        "templates_project": legacy["templates_project"],
        "templates_dir": config.DEFAULT_TEMPLATES_DIR,
    }


def _load() -> dict:
    raw = load_json(config.SETTINGS_FILE, {})
    if raw and "default" not in raw and "users" not in raw:
        raw = {"default": raw, "users": {}}     # Migration Altformat
    return {"default": {**_base_default(), **(raw.get("default") or {})},
            "users": raw.get("users") or {}}


_settings = _load()


def effective(username: str | None) -> dict:
    """Standard, überlagert mit den persönlichen Werten des Benutzers."""
    d = dict(_settings["default"])
    own_token = False
    if username:
        overrides = _settings["users"].get(username.lower()) or {}
        for key, value in overrides.items():
            if key == "selected_groups":
                d[key] = value                  # auch [] = "alle" gilt
            elif value not in (None, ""):
                d[key] = value
        own_token = bool(overrides.get("private_token"))
    d["_own_token"] = own_token
    d["_user"] = username
    return d


def set_context(username: str | None) -> None:
    _ctx.set(effective(username))


def current() -> dict:
    ctx = _ctx.get()
    return ctx if ctx is not None else effective(None)


def generation() -> int:
    return _generation


def scope_key() -> str:
    """Cache-Namespace je Verbindung/Sichtbarkeit (URL, Token, Gruppe, Auswahl)."""
    s = current()
    raw = "|".join([s["gitlab_url"], s["private_token"], s["group_path"],
                    ",".join(s.get("selected_groups") or [])])
    return hashlib.sha1(raw.encode()).hexdigest()[:10]


def default_token_set() -> bool:
    return bool(_settings["default"]["private_token"])


def update(username: str, body: dict[str, Any], *, as_default: bool) -> None:
    """Persönliche Overrides bzw. (Admin) die Standard-Konfiguration ändern."""
    global _generation
    with _lock:
        target = (_settings["default"] if as_default
                  else _settings["users"].setdefault(username.lower(), {}))
        if body.get("gitlab_url"):
            target["gitlab_url"] = body["gitlab_url"].strip()
        if body.get("token"):                   # leer = unverändert lassen
            target["private_token"] = body["token"]
        if body.get("clear_token") and not as_default:
            target.pop("private_token", None)   # zurück zum Standard-Token
        if body.get("group_path"):
            target["group_path"] = body["group_path"].strip().strip("/")
        if "selected_groups" in body and body["selected_groups"] is not None:
            target["selected_groups"] = list(body["selected_groups"])
        if body.get("templates_project") is not None:
            target["templates_project"] = (body["templates_project"] or "").strip().strip("/")
        if body.get("templates_dir") is not None:
            target["templates_dir"] = ((body["templates_dir"] or "").strip().strip("/")
                                       or config.DEFAULT_TEMPLATES_DIR)
        write_private(config.SETTINGS_FILE, _settings)
        _generation += 1                        # GitLab-Clients invalidieren
