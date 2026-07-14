"""Active-Directory-Anmeldung per LDAP(S)-Bind mit erzwungener Zertifikatsprüfung."""

from __future__ import annotations

import logging
import os
import ssl
from typing import Optional

from . import config
from .storage import load_json, write_private

log = logging.getLogger("cifc.ad")

_DEFAULTS = {
    "ad_enabled": False,
    "ad_server": "",           # z. B. ldaps://dc1.example.internal
    "ad_upn_suffix": "",       # z. B. example.internal -> Bind als user@example.internal
    "ad_base_dn": "",          # z. B. DC=example,DC=internal (für Gruppenprüfung)
    "ad_admin_group": "",      # DN der Gruppe mit Admin-Rechten
    "ad_user_group": "",       # optional: DN, ohne die der Login verweigert wird
}


def load_cfg() -> dict:
    return {**_DEFAULTS, **load_json(config.AUTHCFG_FILE, {})}


def save_cfg(body: dict) -> dict:
    cfg = load_cfg()
    for key in _DEFAULTS:
        if key in body:
            cfg[key] = bool(body[key]) if key == "ad_enabled" else str(body[key]).strip()
    write_private(config.AUTHCFG_FILE, cfg)
    return cfg


def _escape_filter(value: str) -> str:
    for char, repl in (("\\", r"\5c"), ("*", r"\2a"), ("(", r"\28"),
                       (")", r"\29"), ("\0", r"\00")):
        value = value.replace(char, repl)
    return value


def authenticate(username: str, password: str) -> Optional[dict]:
    """Bind gegen AD. Rückgabe {'role': ...} bei Erfolg, sonst None."""
    cfg = load_cfg()
    if not cfg["ad_enabled"] or not cfg["ad_server"] or not password:
        return None
    result = test_connection(cfg, username, password)
    return {"role": result["role"]} if result.get("ok") else None


def test_connection(cfg: dict, username: str, password: str) -> dict:
    """Verbindungstest mit sprechender Diagnose – nutzt authenticate() mit.

    Rückgabe immer {'ok': bool, 'message': str, ggf. 'role', 'bind_user'};
    das Test-Passwort wird weder gespeichert noch geloggt."""
    try:
        import ldap3
        from ldap3.core.exceptions import LDAPBindError, LDAPSocketOpenError
    except ImportError:
        return {"ok": False, "message": "ldap3 nicht installiert"}
    if not cfg.get("ad_server"):
        return {"ok": False, "message": "Kein AD-Server angegeben"}
    if not username or not password:
        return {"ok": False, "message": "Testbenutzer und Passwort angeben"}

    bind_user = (f"{username}@{cfg['ad_upn_suffix']}"
                 if cfg.get("ad_upn_suffix") else username)
    tls = None
    if cfg["ad_server"].lower().startswith("ldaps://"):
        # ldap3 validiert standardmäßig NICHT -> hier erzwingen.
        tls = ldap3.Tls(validate=ssl.CERT_REQUIRED,
                        ca_certs_file=os.environ.get("SSL_CERT_FILE") or None)
    try:
        server = ldap3.Server(cfg["ad_server"], connect_timeout=6, tls=tls)
        conn = ldap3.Connection(server, user=bind_user, password=password,
                                auto_bind=True, receive_timeout=10)
    except LDAPSocketOpenError as e:
        return {"ok": False,
                "message": f"Server {cfg['ad_server']} nicht erreichbar "
                           f"(Netz/Port/Zertifikat?): {e}"}
    except LDAPBindError:
        return {"ok": False,
                "message": f"Bind als {bind_user} abgelehnt – "
                           f"Benutzer/Passwort oder UPN-Suffix prüfen"}
    except Exception as e:
        return {"ok": False, "message": f"Verbindung fehlgeschlagen: {e}"}

    role = "user"
    group_info = "ohne Gruppenprüfung (Base-DN leer)"
    try:
        if cfg.get("ad_base_dn"):
            flt = (f"(&(objectClass=user)(|(sAMAccountName={_escape_filter(username)})"
                   f"(userPrincipalName={_escape_filter(bind_user)})))")
            conn.search(cfg["ad_base_dn"], flt, attributes=["memberOf"])
            groups = ([str(g).lower() for g in (conn.entries[0].memberOf.values or [])]
                      if conn.entries else [])
            group_info = f"{len(groups)} Gruppenmitgliedschaften geprüft"
            admin_grp = (cfg.get("ad_admin_group") or "").lower()
            user_grp = (cfg.get("ad_user_group") or "").lower()
            if admin_grp and admin_grp in groups:
                role = "admin"
            elif user_grp and user_grp not in groups:
                return {"ok": False,
                        "message": f"Bind erfolgreich, aber {username} ist nicht "
                                   f"Mitglied der Zugriffs-Gruppe ({group_info})"}
    finally:
        try:
            conn.unbind()
        except Exception:
            pass
    return {"ok": True, "role": role, "bind_user": bind_user,
            "message": f"Bind als {bind_user} erfolgreich, {group_info}"}
