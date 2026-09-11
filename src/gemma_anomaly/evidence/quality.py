"""Freshness, coverage, and staleness flags.

Missing data is a first class result. It is never filled in silently and a
carried forward value never bridges a long gap.
"""
from __future__ import annotations

from datetime import datetime

from ..contracts.snapshot import EvidenceItem, EvidenceKind, Freshness
from ..settings import site


def _parse(ts) -> datetime | None:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(str(ts).replace("Z", ""))


def freshness(rows: list[dict], decision_time: datetime,
              expected_period_s: float, ts_key: str = "ts") -> Freshness:
    stale_after = float(site()["evidence_quality"]["stale_after_s"])
    if not rows:
        return Freshness(age_s=float("inf"), expected_period_s=expected_period_s,
                         stale=True, gap_count=0, frozen=False)

    stamps = [t for t in (_parse(r.get(ts_key)) for r in rows) if t]
    if not stamps:
        return Freshness(age_s=float("inf"), expected_period_s=expected_period_s,
                         stale=True)

    last = max(stamps)
    age = (decision_time - last).total_seconds()

    gaps = 0
    ordered = sorted(stamps)
    for a, b in zip(ordered, ordered[1:]):
        if (b - a).total_seconds() > expected_period_s * 5:
            gaps += 1

    values = [r.get("w") for r in rows if r.get("w") is not None]
    frozen = len(values) >= 60 and len(set(values[-60:])) == 1

    return Freshness(age_s=age, expected_period_s=expected_period_s,
                     stale=age > stale_after, gap_count=gaps, frozen=frozen)


def carry_forward_allowed(age_s: float) -> bool:
    return age_s <= float(site()["evidence_quality"]["max_carry_forward_s"])


def quality_evidence(table: str, rows: int, last_ts, decision_time: datetime
                     ) -> EvidenceItem:
    last = _parse(last_ts)
    age = (decision_time - last).total_seconds() if last else float("inf")
    return EvidenceItem(
        id=f"dq.{table}",
        kind=EvidenceKind.DERIVED,
        label=f"{table} coverage",
        value=rows,
        unit="rows",
        source=f"anylog:{table}",
        at=last or decision_time,
        freshness=Freshness(
            age_s=age,
            expected_period_s=1.0,
            stale=age > float(site()["evidence_quality"]["stale_after_s"]),
        ),
        note="Row count and last timestamp inside the assessed window.",
    )
