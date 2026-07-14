"""Flüchtiger Datei-Cache (JSON-Textdateien) mit TTL und Verbindungs-Scope."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from . import config, settings_store


def _path(name: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_",
                  f"{settings_store.scope_key()}__{name}")
    return config.CACHE_DIR / f"{safe}.json"


def get(name: str, ttl: int) -> Any:
    p = _path(name)
    try:
        if p.exists() and (time.time() - p.stat().st_mtime) < ttl:
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def put(name: str, data: Any) -> Any:
    _path(name).write_text(json.dumps(data, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    return data


def invalidate(name: str) -> None:
    _path(name).unlink(missing_ok=True)


def clear_all() -> int:
    n = 0
    for f in config.CACHE_DIR.glob("*.json"):
        f.unlink(missing_ok=True)
        n += 1
    return n


def info() -> dict:
    files = list(config.CACHE_DIR.glob("*.json"))
    return {"files": len(files), "bytes": sum(f.stat().st_size for f in files)}


# ---------------------------------------------------- Stale-While-Revalidate

import contextvars as _contextvars
import threading as _threading

_refreshing: set[str] = set()
_refresh_lock = _threading.Lock()


def get_with_stale(name: str, ttl: int) -> tuple[Any, bool]:
    """Liefert (Daten, frisch?) – auch abgelaufene Daten, statt None.

    Grundlage für Stale-While-Revalidate: Der Aufrufer kann veraltete Daten
    sofort ausliefern und den Neuaufbau in den Hintergrund verlagern."""
    p = _path(name)
    try:
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            fresh = (time.time() - p.stat().st_mtime) < ttl
            return data, fresh
    except Exception:
        pass
    return None, False


def refresh_in_background(name: str, builder) -> None:
    """Baut einen Cache-Eintrag in einem Daemon-Thread neu auf.

    Ein Guard je (Scope, Name) verhindert, dass parallele Requests denselben
    teuren Neuaufbau mehrfach anstoßen (Thundering Herd)."""
    key = f"{settings_store.scope_key()}::{name}"
    with _refresh_lock:
        if key in _refreshing:
            return
        _refreshing.add(key)
    ctx = _contextvars.copy_context()          # Benutzer-Konfiguration mitnehmen

    def run() -> None:
        try:
            ctx.run(builder)
        except Exception:
            pass
        finally:
            with _refresh_lock:
                _refreshing.discard(key)

    _threading.Thread(target=run, daemon=True, name=f"refresh-{name}").start()
