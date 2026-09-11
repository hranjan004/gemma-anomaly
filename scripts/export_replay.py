#!/usr/bin/env python3
"""Freeze a range of snapshots to disk as the demo backup."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gemma_anomaly.evidence import anylog          # noqa: E402
from gemma_anomaly.replay.export import export_range  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=6.0)
    ap.add_argument("--step-minutes", type=int, default=10)
    ap.add_argument("--window-minutes", type=int, default=30)
    ap.add_argument("--name", default="demo")
    args = ap.parse_args()

    end = anylog.latest_timestamp("power") or datetime.now()
    start = end - timedelta(hours=args.hours)
    out = export_range(start, end, args.step_minutes, args.window_minutes, args.name)
    print(f"exported to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
