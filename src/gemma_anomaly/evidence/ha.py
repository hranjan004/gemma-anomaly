"""Home Assistant equipment context.

Home Assistant normally sits on the building's own LAN and is not reachable
from outside it, so this provider has to run on a host inside that network or
behind a proxy. Set HA_URL and HA_TOKEN (or HA_TOKEN_FILE); there is no default
address on purpose.

When Home Assistant is unreachable the snapshot records its entities as
unavailable rather than omitting them, so an agent can tell "no leak sensor"
from "leak sensor says dry".

Observation only. Control is a separate workflow with its own authorization.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from ..contracts.snapshot import EquipmentContext
from ..settings import site

COMMANDED_DOMAINS = {"climate", "input_number", "input_boolean", "scene", "script"}


def _token() -> str | None:
    tok = os.environ.get("HA_TOKEN")
    if tok:
        return tok
    path = Path(os.environ.get("HA_TOKEN_FILE", str(Path.home() / "ha_token.txt")))
    return path.read_text().strip() if path.exists() else None


def _base() -> str:
    return os.environ.get(
        "HA_URL", site()["home_assistant"].get("default_url") or ""
    ).rstrip("/")


def configured() -> bool:
    return bool(_base())


def reachable(timeout: int = 5) -> bool:
    if not configured():
        return False
    try:
        req = urllib.request.Request(f"{_base()}/api/",
                                     headers={"Authorization": f"Bearer {_token()}"})
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False


def get_equipment_context(entity_ids: list[str], timeout: int = 5
                          ) -> list[EquipmentContext]:
    token = _token() if configured() else None
    out: list[EquipmentContext] = []
    for eid in entity_ids:
        domain = eid.split(".", 1)[0]
        if not token:
            out.append(EquipmentContext(entity_id=eid, state=None, available=False,
                                        commanded=domain in COMMANDED_DOMAINS))
            continue
        try:
            req = urllib.request.Request(
                f"{_base()}/api/states/{eid}",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode())
            out.append(EquipmentContext(
                entity_id=eid,
                state=body.get("state"),
                commanded=domain in COMMANDED_DOMAINS,
                available=body.get("state") not in (None, "unavailable", "unknown"),
                at=datetime.fromisoformat(body["last_updated"].replace("Z", "+00:00"))
                if body.get("last_updated") else None,
            ))
        except Exception:
            out.append(EquipmentContext(entity_id=eid, state=None, available=False,
                                        commanded=domain in COMMANDED_DOMAINS))
    return out
