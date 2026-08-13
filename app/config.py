"""Zentrale Konfiguration: Pfade, Konstanten, Umgebungsvariablen.

Alles Veränderliche (Settings, Benutzer, Cache) lebt unter DATA_DIR,
damit der Docker-Betrieb mit einem einzigen Volume auskommt.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", APP_ROOT))
STATIC_DIR = APP_ROOT / "static"

CACHE_DIR = DATA_DIR / "cache"
SETTINGS_FILE = DATA_DIR / "settings.json"
USERS_FILE = DATA_DIR / "users.json"
AUTHCFG_FILE = DATA_DIR / "auth.json"
MAINTENANCE_TAGS_FILE = DATA_DIR / "maintenance_tags.json"

CI_FILE = ".gitlab-ci.yml"
DEFAULT_TEMPLATES_DIR = "standard"      # Ordner im ci-templates-Projekt

# Cache-Lebensdauern (Sekunden)
TTL_TREE = 300
TTL_PIPELINES = 45
TTL_VERSIONS = 300
TTL_TEMPLATES = 600
TTL_GROUP_VARS = 300
TTL_GROUP_JOBS = 90

WORKERS = 16                            # parallele GitLab-Requests

# Wartungsmodus: apt-update/apt-upgrade/cron-stop (Linux) liegen hinter dem
# manuellen Trigger-Job "Wartung" (Kind-Pipeline) statt direkt in der obersten
# Pipeline-Ebene - erst starten, dann auf die Kind-Pipeline-Jobs warten.
MAINT_BRIDGE_NAME = "Wartung"
MAINT_BRIDGE_POLL_ATTEMPTS = 6
MAINT_BRIDGE_POLL_INTERVAL = 2.0        # Sekunden zwischen den Versuchen
SPARK_COUNT = 5                         # Pipelines je Projekt in der Baum-Sparkline
GITLAB_TIMEOUT = 20

SESSION_COOKIE = "cifc_session"
SESSION_TTL = 12 * 3600                 # 12 h gleitend
SESSION_SECURE = os.environ.get("SESSION_SECURE", "0") == "1"

LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_SECONDS = 300


def legacy_config() -> dict:
    """Fallback auf eine alte config.py (nur Erststart-Migration)."""
    try:
        import config  # type: ignore
        return {
            "gitlab_url": getattr(config, "GITLAB_URL", "") or "",
            "private_token": getattr(config, "PRIVATE_TOKEN", "") or "",
            "group_path": (getattr(config, "GROUP_PATH", "") or "").strip("/"),
            "templates_project": getattr(config, "TEMPLATES_PROJECT", "") or "",
        }
    except ImportError:
        return {"gitlab_url": "", "private_token": "",
                "group_path": "", "templates_project": ""}


DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
