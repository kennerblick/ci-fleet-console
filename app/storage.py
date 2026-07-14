"""Dateibasierte JSON-Ablage mit restriktiven Rechten (0600)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("cifc.storage")


def load_json(path: Path, default: Any) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            log.exception("Kann %s nicht lesen – nutze Default", path)
    return default


def write_private(path: Path, data: Any) -> None:
    """Schreibt JSON und beschränkt den Zugriff auf den Besitzer."""
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        log.warning("chmod 600 auf %s nicht möglich", path)
