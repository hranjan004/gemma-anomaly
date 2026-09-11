"""Incident level evaluation.

Definitions are fixed here before results are looked at. All monitored time goes
into the false alert rate denominator, not only the time that produced alerts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..contracts.findings import Category, Incident

MATCH_TOLERANCE = timedelta(minutes=15)


@dataclass
class LabeledEvent:
    start: datetime
    end: datetime
    category: Category
    equipment: str | None = None
    provenance: str = "verified"          # verified | weak | synthetic


@dataclass
class Report:
    monitored_hours: float
    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0
    abstentions: int = 0
    call_failures: int = 0
    detection_delays_s: list[float] = field(default_factory=list)
    by_provenance: dict[str, int] = field(default_factory=dict)

    @property
    def precision(self) -> float | None:
        denom = self.true_positive + self.false_positive
        return self.true_positive / denom if denom else None

    @property
    def recall(self) -> float | None:
        denom = self.true_positive + self.false_negative
        return self.true_positive / denom if denom else None

    @property
    def false_alerts_per_day(self) -> float | None:
        return (self.false_positive / (self.monitored_hours / 24.0)
                if self.monitored_hours else None)

    @property
    def median_detection_delay_s(self) -> float | None:
        if not self.detection_delays_s:
            return None
        ordered = sorted(self.detection_delays_s)
        return ordered[len(ordered) // 2]


def _matches(inc: Incident, ev: LabeledEvent) -> bool:
    if inc.headline_category is not ev.category:
        return False
    if ev.equipment and ev.equipment not in inc.equipment:
        return False
    return (inc.interval_start <= ev.end + MATCH_TOLERANCE
            and inc.interval_end >= ev.start - MATCH_TOLERANCE)


def score(incidents: list[Incident], events: list[LabeledEvent],
          monitored_hours: float) -> Report:
    report = Report(monitored_hours=monitored_hours)
    unmatched = list(events)

    for inc in incidents:
        if inc.headline_category is Category.INSUFFICIENT_EVIDENCE:
            report.abstentions += 1
            continue
        if inc.headline_category is Category.NORMAL:
            continue
        report.call_failures += len(inc.panels_failed)

        hit = next((ev for ev in unmatched if _matches(inc, ev)), None)
        if hit is None:
            report.false_positive += 1
            continue
        report.true_positive += 1
        report.by_provenance[hit.provenance] = report.by_provenance.get(hit.provenance, 0) + 1
        report.detection_delays_s.append(
            max(0.0, (inc.decision_time - hit.start).total_seconds())
        )
        unmatched.remove(hit)

    report.false_negative = len(unmatched)
    return report


def compare(rows: dict[str, Report]) -> dict[str, dict]:
    """Side by side for rules only, untuned, and tuned on the same inputs."""
    return {
        name: {
            "precision": r.precision,
            "recall": r.recall,
            "false_alerts_per_day": r.false_alerts_per_day,
            "median_detection_delay_s": r.median_detection_delay_s,
            "abstentions": r.abstentions,
            "call_failures": r.call_failures,
            "by_provenance": r.by_provenance,
        }
        for name, r in rows.items()
    }
