"""Derived features computed in ordinary code.

The model is never asked to count switches, sum energy, or compute a deviation.
It is given the numbers and asked to judge them.
"""
from __future__ import annotations

import statistics
from datetime import datetime

from ..contracts.snapshot import DerivedFeatures


def _parse(ts) -> datetime:
    return ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts).replace("Z", ""))


def state_series(rows: list[dict], appliance: str) -> list[tuple[datetime, bool]]:
    return [
        (_parse(r["ts"]), str(r.get("state", "")).strip().lower() == "on")
        for r in rows
        if r.get("appliance") == appliance
    ]


def derive(rows: list[dict], appliance: str, power: list[dict] | None = None,
           baseline_w: float | None = None) -> DerivedFeatures:
    series = state_series(rows, appliance)
    if not series:
        return DerivedFeatures()

    series.sort(key=lambda x: x[0])
    span_s = (series[-1][0] - series[0][0]).total_seconds() or 1.0

    switches = sum(1 for a, b in zip(series, series[1:]) if a[1] != b[1])
    on_points = sum(1 for _, s in series if s)
    duty = on_points / len(series)

    # Longest trailing contiguous on run, in seconds.
    run_s = 0.0
    if series[-1][1]:
        idx = len(series) - 1
        while idx > 0 and series[idx - 1][1]:
            idx -= 1
        run_s = (series[-1][0] - series[idx][0]).total_seconds()

    watts = [float(r["avg_w"]) for r in rows
             if r.get("appliance") == appliance and r.get("avg_w") is not None]
    energy_wh = (statistics.fmean(watts) * span_s / 3600.0) if watts else None

    sigma = None
    if baseline_w is not None and watts:
        spread = statistics.pstdev(watts) if len(watts) > 1 else 0.0
        if spread > 0:
            sigma = (statistics.fmean(watts) - baseline_w) / spread

    return DerivedFeatures(
        run_duration_s=run_s,
        switch_count=switches,
        switches_per_h=switches / (span_s / 3600.0),
        energy_wh=energy_wh,
        baseline_w=baseline_w,
        deviation_sigma=sigma,
        duty_cycle=duty,
    )


def downsample(rows: list[dict], max_points: int = 60) -> list[dict]:
    """Compact sequence for the prompt. Never send the whole archive."""
    if len(rows) <= max_points:
        return rows
    step = len(rows) / max_points
    return [rows[int(i * step)] for i in range(max_points)]


def hour_baseline(rows: list[dict], decision_time: datetime) -> float | None:
    """Median panel watts for the same hour of day across the supplied history."""
    same_hour = [float(r["w"]) for r in rows
                 if r.get("w") is not None and _parse(r["ts"]).hour == decision_time.hour]
    return statistics.median(same_hour) if same_hour else None
