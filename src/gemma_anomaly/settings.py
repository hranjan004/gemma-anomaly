"""Runtime settings. Everything overridable by environment variable."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"


SITE_PATH = CONFIG_DIR / "site.yaml"
SITE_EXAMPLE_PATH = CONFIG_DIR / "site.example.yaml"


@lru_cache(maxsize=None)
def site() -> dict[str, Any]:
    """Load the local site config, falling back to the committed example.

    config/site.yaml is gitignored. It holds panel and appliance mappings for a
    specific building and host addresses for a specific private network, so it
    stays on the machine that owns the deployment.
    """
    path = SITE_PATH if SITE_PATH.exists() else SITE_EXAMPLE_PATH
    with open(path) as fh:
        cfg = yaml.safe_load(fh)
    cfg["_config_path"] = str(path.name)
    cfg["_is_example"] = path == SITE_EXAMPLE_PATH
    return cfg


def using_example_config() -> bool:
    return bool(site().get("_is_example"))


@lru_cache(maxsize=None)
def categories() -> dict[str, Any]:
    with open(CONFIG_DIR / "categories.yaml") as fh:
        return yaml.safe_load(fh)


def anylog_host() -> str:
    return os.environ.get("ANYLOG_HOST", site()["anylog"]["default_host"])


def anylog_port() -> int:
    return int(os.environ.get("ANYLOG_REST_PORT", site()["anylog"]["rest_port"]))


def panel_for_appliance(appliance: str) -> str | None:
    for pid, cfg in site()["panels"].items():
        if appliance in cfg["appliances"]:
            return pid
    return None


def panel_channel(panel_id: str) -> str:
    return site()["panels"][panel_id]["channel"]


def is_measured(appliance: str) -> bool:
    return appliance in site()["evidence_quality"]["measured"]


SERVING_BASE_URL = os.environ.get("GEMMA_BASE_URL", "http://127.0.0.1:8001/v1")
SERVING_MODEL = os.environ.get("GEMMA_MODEL", "")
SERVING_ADAPTER = os.environ.get("GEMMA_ADAPTER", "")
RESPAN_BASE_URL = os.environ.get("RESPAN_BASE_URL", "")
RESPAN_API_KEY = os.environ.get("RESPAN_API_KEY", "")
NANGO_BASE_URL = os.environ.get("NANGO_BASE_URL", "https://api.nango.dev")
NANGO_SECRET_KEY = os.environ.get("NANGO_SECRET_KEY", "")
NANGO_CONNECTION_ID = os.environ.get("NANGO_CONNECTION_ID", "")
REVIEW_SHEET_ID = os.environ.get("REVIEW_SHEET_ID", "")
