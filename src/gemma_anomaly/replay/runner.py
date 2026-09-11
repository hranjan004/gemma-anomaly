"""Replay a saved snapshot through the same agents and coordinator."""
from __future__ import annotations

import json
from pathlib import Path

from ..contracts.findings import Incident
from ..contracts.snapshot import HouseholdSnapshot
from ..coordinator import workflow
from ..serving.client import Route


def load_snapshot(path: str | Path) -> HouseholdSnapshot:
    return HouseholdSnapshot.model_validate_json(Path(path).read_text())


def replay_one(path: str | Path, route: Route | None = None) -> list[Incident]:
    return workflow.assess(load_snapshot(path), route)


def replay_set(dir_path: str | Path, route: Route | None = None) -> list[Incident]:
    directory = Path(dir_path)
    manifest = json.loads((directory / "manifest.json").read_text())
    out: list[Incident] = []
    for entry in manifest["snapshots"]:
        out += replay_one(directory / entry["file"], route)
    return out
