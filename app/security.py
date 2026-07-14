"""Lokale Benutzer, Passwort-Hashing (scrypt), Sessions, Brute-Force-Schutz."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import threading
import time
from typing import Optional

from . import config
from .storage import load_json, write_private

log = logging.getLogger("cifc.security")

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{2,64}$")
MIN_PASSWORD_LEN = 8

_lock = threading.Lock()
_sessions: dict[str, dict] = {}          # token -> {user, role, source, exp}
_failed: dict[str, dict] = {}            # key -> {count, until}


# ------------------------------------------------------------------ Passwörter

def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt,
                            n=2 ** 14, r=8, p=1, dklen=32)
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    try:
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                                n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(digest.hex(), hash_hex)
    except Exception:
        return False


# ------------------------------------------------------------------- Benutzer

def load_users() -> dict:
    return load_json(config.USERS_FILE, {"users": []})


def save_users(data: dict) -> None:
    write_private(config.USERS_FILE, data)


def find_local_user(username: str) -> Optional[dict]:
    for u in load_users()["users"]:
        if u["username"].lower() == username.lower() and u["source"] == "local":
            return u
    return None


def bootstrap_admin() -> None:
    """Beim Erststart einen lokalen Admin anlegen (Passwort aus ENV oder generiert)."""
    data = load_users()
    if data["users"]:
        return
    password = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(12)
    salt, digest = hash_password(password)
    data["users"].append({"username": "admin", "role": "admin",
                          "source": "local", "salt": salt, "hash": digest})
    save_users(data)
    shown = "aus ENV ADMIN_PASSWORD" if os.environ.get("ADMIN_PASSWORD") else password
    log.warning("[AUTH] Erststart: lokaler Benutzer 'admin' angelegt, Passwort: %s", shown)
    print(f"[AUTH] Erststart: lokaler Benutzer 'admin' angelegt, Passwort: {shown}",
          flush=True)


# ------------------------------------------------------------------- Sessions

def create_session(user: str, role: str, source: str) -> str:
    token = secrets.token_urlsafe(32)
    with _lock:
        _sessions[token] = {"user": user, "role": role, "source": source,
                            "exp": time.time() + config.SESSION_TTL}
    return token


def get_session(token: str | None) -> Optional[dict]:
    if not token:
        return None
    with _lock:
        session = _sessions.get(token)
        if not session:
            return None
        if session["exp"] < time.time():
            _sessions.pop(token, None)
            return None
        session["exp"] = time.time() + config.SESSION_TTL   # gleitend verlängern
        return session


def drop_session(token: str | None) -> None:
    with _lock:
        _sessions.pop(token, None)


def drop_sessions_of(username: str) -> None:
    with _lock:
        for token in [t for t, s in _sessions.items()
                      if s["user"].lower() == username.lower()]:
            _sessions.pop(token, None)


# -------------------------------------------------------------- Brute-Force

def rate_key(client_ip: str, username: str) -> str:
    return f"{client_ip}|{username.lower()}"


def rate_blocked(key: str) -> bool:
    entry = _failed.get(key)
    return bool(entry and entry["until"] > time.time())


def rate_fail(key: str) -> None:
    entry = _failed.setdefault(key, {"count": 0, "until": 0})
    entry["count"] += 1
    if entry["count"] >= config.LOGIN_MAX_FAILURES:
        entry["until"] = time.time() + config.LOGIN_LOCKOUT_SECONDS
        entry["count"] = 0
        log.warning("Login-Sperre aktiv für %s", key)


def rate_reset(key: str) -> None:
    _failed.pop(key, None)
