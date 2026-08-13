"""Wartungs-Tags (Bulk-Update/Bulk-Reboot) je Projekt.

Globaler, geteilter Fleet-Zustand (nicht pro Benutzer) – anders als
settings_store.py gibt es hier keine ContextVar-Auflösung.
"""

from __future__ import annotations

import threading
from typing import Any

from fastapi import HTTPException

from . import config
from .storage import load_json, write_private

SERVER_GROUPS = ("linux-intern", "linux-extern", "windows")

_lock = threading.Lock()
_tags: dict[str, dict] = load_json(config.MAINTENANCE_TAGS_FILE, {})


def get_all() -> dict[str, dict]:
    return dict(_tags)


def set_tag(project_id: int, update: bool, reboot: bool,
           server_group: str | None) -> dict[str, Any] | None:
    """Setzt oder entfernt den Wartungs-Tag eines Projekts.

    Reboot impliziert Update. Bei aktivem Tag muss server_group gültig sein.
    Sind beide Flags False, wird der Eintrag entfernt (Rückgabe None)."""
    if reboot:
        update = True
    key = str(project_id)
    with _lock:
        if not update and not reboot:
            _tags.pop(key, None)
            write_private(config.MAINTENANCE_TAGS_FILE, _tags)
            return None
        if server_group not in SERVER_GROUPS:
            raise HTTPException(400, f"Ungültige Servergruppe: {server_group}")
        entry = {"update": update, "reboot": reboot, "server_group": server_group}
        _tags[key] = entry
        write_private(config.MAINTENANCE_TAGS_FILE, _tags)
        return entry
