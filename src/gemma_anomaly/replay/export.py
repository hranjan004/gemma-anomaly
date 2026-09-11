"""Freeze a time range to disk as a fixed replay input.

A saved snapshot must recreate the same request independently of the live house.
This is the backup for when connectivity to the deployment host fails.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from ..settings import REPO_ROOT
from ..snapshot.builder import build

REPLAY_DIR = REPO_ROOT / "replay_data"


def export_range(start: datetime, end: datetime, step_minutes: int = 5,
                 window_minutes: int = 30, name: str = "replay",
                 out_dir: Path | None = None) -> Path:
    out_dir = out_dir or (REPLAY_DIR / name)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": name,
        "exported_at": datetime.now().isoformat(),
        "range": [start.isoformat(), end.isoformat()],
        "step_minutes": step_minutes,
        "window_minutes": window_minutes,
        "snapshots": [],
    }

    cursor = start
    while cursor <= end:
        snap = build(decision_time=cursor, window_minutes=window_minutes,
                     mode="replay")
        path = out_dir / f"{snap.snapshot_id}.json"
        path.write_text(snap.model_dump_json(indent=2))
        manifest["snapshots"].append(
            {"snapshot_id": snap.snapshot_id, "decision_time": cursor.isoformat(),
             "file": path.name}
        )
        cursor += timedelta(minutes=step_minutes)

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return out_dir
