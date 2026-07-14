"""Benutzerverwaltung und AD-Konfiguration (nur Administratoren)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import ad, security
from ..deps import admin_required
from ..schemas import AuthCfgBody, AuthCfgTestBody, PasswordBody, UserCreateBody

router = APIRouter(prefix="/api", tags=["users"],
                   dependencies=[Depends(admin_required)])


@router.get("/users")
def list_users():
    return {"users": [{"username": u["username"], "role": u["role"],
                       "source": u["source"]}
                      for u in security.load_users()["users"]]}


@router.post("/users")
def add_user(body: UserCreateBody):
    username = body.username.strip()
    role = body.role if body.role in ("admin", "user") else "user"
    if not security.USERNAME_RE.fullmatch(username):
        raise HTTPException(400, "Ungültiger Benutzername")
    if len(body.password) < security.MIN_PASSWORD_LEN:
        raise HTTPException(400, f"Passwort: mindestens {security.MIN_PASSWORD_LEN} Zeichen")
    data = security.load_users()
    if any(u["username"].lower() == username.lower() for u in data["users"]):
        raise HTTPException(400, "Benutzer existiert bereits")
    salt, digest = security.hash_password(body.password)
    data["users"].append({"username": username, "role": role,
                          "source": "local", "salt": salt, "hash": digest})
    security.save_users(data)
    return {"ok": True}


@router.delete("/users/{username}")
def delete_user(username: str):
    data = security.load_users()
    users = data["users"]
    target = next((u for u in users
                   if u["username"].lower() == username.lower()), None)
    if not target:
        raise HTTPException(404, "Benutzer nicht gefunden")
    local_admins = [u for u in users
                    if u["role"] == "admin" and u["source"] == "local"]
    if target in local_admins and len(local_admins) == 1:
        raise HTTPException(400, "Der letzte lokale Admin kann nicht gelöscht werden")
    users.remove(target)
    security.save_users(data)
    security.drop_sessions_of(username)
    return {"ok": True}


@router.post("/users/{username}/password")
def set_password(username: str, body: PasswordBody):
    if len(body.password) < security.MIN_PASSWORD_LEN:
        raise HTTPException(400, f"Passwort: mindestens {security.MIN_PASSWORD_LEN} Zeichen")
    data = security.load_users()
    for u in data["users"]:
        if u["username"].lower() == username.lower() and u["source"] == "local":
            u["salt"], u["hash"] = security.hash_password(body.password)
            security.save_users(data)
            return {"ok": True}
    raise HTTPException(404, "Lokaler Benutzer nicht gefunden")


@router.get("/authcfg")
def get_authcfg():
    return ad.load_cfg()


@router.post("/authcfg")
def save_authcfg(body: AuthCfgBody):
    return ad.save_cfg(body.model_dump(exclude_none=True))


@router.post("/authcfg/test")
def test_authcfg(body: AuthCfgTestBody):
    """Testet die AD-Anmeldung mit den (noch nicht gespeicherten) Formularwerten.
    Antwortet immer 200 mit ok/message; das Test-Passwort wird nicht gespeichert."""
    cfg = {**ad.load_cfg(),
           "ad_server": body.ad_server.strip(),
           "ad_upn_suffix": body.ad_upn_suffix.strip(),
           "ad_base_dn": body.ad_base_dn.strip(),
           "ad_admin_group": body.ad_admin_group.strip(),
           "ad_user_group": body.ad_user_group.strip()}
    return ad.test_connection(cfg, body.username.strip(), body.password)
