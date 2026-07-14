"""GitLab-Zugriff: ein Client je Thread und Verbindung, kontextfeste Worker."""

from __future__ import annotations

import contextvars
import threading
from concurrent.futures import Executor, Future
from typing import Any, Callable

import gitlab
from fastapi import HTTPException

from . import config, settings_store

_tls = threading.local()


def gl() -> gitlab.Gitlab:
    s = settings_store.current()
    url, token = s["gitlab_url"], s["private_token"]
    if not url or not token:
        raise HTTPException(400, "GitLab nicht konfiguriert – bitte ⚙ Konfiguration öffnen")
    clients: dict = getattr(_tls, "clients", None) or {}
    _tls.clients = clients
    key = (url, token, settings_store.generation())
    client = clients.get(key)
    if client is None:
        clients.clear()
        client = clients[key] = gitlab.Gitlab(url, private_token=token,
                                              timeout=config.GITLAB_TIMEOUT)
    return client


def ctx_submit(executor: Executor, fn: Callable, *args: Any) -> Future:
    """Task mit kopiertem Context abschicken, damit settings_store.current()
    auch im Worker-Thread die Konfiguration des Benutzers sieht."""
    return executor.submit(contextvars.copy_context().run, fn, *args)
