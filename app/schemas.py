"""Pydantic-Modelle für Request-Bodies (Validierung an der API-Grenze)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)


class UserCreateBody(BaseModel):
    username: str
    password: str
    role: str = "user"


class PasswordBody(BaseModel):
    password: str


class SettingsBody(BaseModel):
    gitlab_url: str | None = None
    token: str | None = None
    clear_token: bool = False
    group_path: str | None = None
    selected_groups: list[str] | None = None
    templates_project: str | None = None
    templates_dir: str | None = None
    as_default: bool = False


class ScanBody(BaseModel):
    gitlab_url: str | None = None
    token: str | None = None
    group_path: str | None = None


class AuthCfgTestBody(BaseModel):
    ad_server: str = ""
    ad_upn_suffix: str = ""
    ad_base_dn: str = ""
    ad_admin_group: str = ""
    ad_user_group: str = ""
    username: str = ""
    password: str = ""


class AuthCfgBody(BaseModel):
    ad_enabled: bool | None = None
    ad_server: str | None = None
    ad_upn_suffix: str | None = None
    ad_base_dn: str | None = None
    ad_admin_group: str | None = None
    ad_user_group: str | None = None


class RunPipelineBody(BaseModel):
    ref: str | None = None
    variables: list[dict] = Field(default_factory=list)


class SaveCiBody(BaseModel):
    content: str = ""
    branch: str | None = None
    message: str | None = None


class CheckContentBody(BaseModel):
    content: str = ""


class VarsSaveBody(BaseModel):
    variables: list[dict] = Field(default_factory=list)
