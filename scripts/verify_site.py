#!/usr/bin/env python3
"""Re-verify every assumption in config/site.yaml against the live deployment.

Run this before trusting the config, and again on the morning of the event.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gemma_anomaly.evidence import anylog          # noqa: E402
from gemma_anomaly.settings import site            # noqa: E402


def main() -> int:
    cfg = site()
    problems: list[str] = []

    health = anylog.health()
    print(f"anylog {health['host']} reachable={health['reachable']} "
          f"dbms_ok={health['databases_ok']}")
    if not health["reachable"]:
        print("FAIL: cannot reach AnyLog")
        return 1

    last = anylog.latest_timestamp("power")
    print(f"latest power sample: {last}")
    if last is None:
        return 1

    start, end = last - timedelta(minutes=15), last

    power = anylog.get_panel_window(
        cfg["channels"]["panels"] + cfg["channels"]["aggregate"], start, end
    )
    for channel, rows in power.items():
        print(f"  {channel:<26} {len(rows):>6} rows")
        if not rows:
            problems.append(f"no rows for channel {channel}")

    for pid, pcfg in cfg["panels"].items():
        rows = anylog.get_appliance_estimates(pcfg["channel"], start, end)
        seen = sorted({r["appliance"] for r in rows})
        expected = sorted(pcfg["appliances"])
        print(f"  {pid} appliances live={len(seen)} expected={len(expected)}")
        missing = set(expected) - set(seen)
        extra = set(seen) - set(expected)
        if missing:
            problems.append(f"{pid} missing appliances in live data: {sorted(missing)}")
        if extra:
            problems.append(f"{pid} live appliances not in config: {sorted(extra)}")

    solar = anylog.get_solar_snapshot(start, end)
    print(f"  solar rows in window: {len(solar)}")
    if not solar:
        problems.append("solar_data has no rows in the window")

    for entry in anylog.get_data_quality(start, end):
        print(f"  dq {entry['table']:<20} rows={entry['rows']:<8} last={entry['last_ts']}")

    if problems:
        print("\nPROBLEMS")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nAll site assumptions verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
