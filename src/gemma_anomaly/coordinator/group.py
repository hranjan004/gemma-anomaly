"""Grouping, deduplication, and incident identity.

Incident matching and alert deduplication are defined here, before any results
are looked at. Changing these definitions invalidates a comparison.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from ..contracts.findings import AgentResult, Category, PanelFinding

MERGE_WINDOW = timedelta(minutes=10)
DEDUP_WINDOW = timedelta(minutes=30)

SEVERITY_ORDER = [
    Category.TELEMETRY_PROBLEM,
    Category.UNEXPECTED_DEMAND,
    Category.PROLONGED_OPERATION,
    Category.UNUSUAL_CYCLING,
    Category.INSUFFICIENT_EVIDENCE,
    Category.NORMAL,
]


def is_actionable(f: PanelFinding) -> bool:
    return f.category not in (Category.NORMAL, Category.INSUFFICIENT_EVIDENCE)


def fingerprint(findings: list[PanelFinding]) -> str:
    key = "|".join(sorted(
        f"{f.panel_id}:{f.category.value}:{f.equipment or '-'}" for f in findings
    ))
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def incident_id(fp: str, bucket_start: datetime) -> str:
    """Stable across retries. The same fingerprint in the same bucket is the
    same incident, so a review row updates instead of duplicating."""
    raw = f"{fp}|{bucket_start.replace(second=0, microsecond=0).isoformat()}"
    return "inc_" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def group(results: list[AgentResult]) -> list[list[PanelFinding]]:
    """Cluster findings that overlap in time and share equipment or interval."""
    findings = [r.finding for r in results if r.finding is not None]
    if not findings:
        return []

    findings.sort(key=lambda f: f.interval_start)
    clusters: list[list[PanelFinding]] = []
    for f in findings:
        placed = False
        for cluster in clusters:
            last = cluster[-1]
            overlaps = f.interval_start - last.interval_end <= MERGE_WINDOW
            related = (
                f.equipment is not None and f.equipment == last.equipment
            ) or f.category == last.category
            if overlaps and related:
                cluster.append(f)
                placed = True
                break
        if not placed:
            clusters.append([f])
    return clusters


def headline(findings: list[PanelFinding]) -> Category:
    for category in SEVERITY_ORDER:
        if any(f.category is category for f in findings):
            return category
    return Category.NORMAL


def suppress_duplicate(fp: str, last_seen: dict[str, datetime],
                       now: datetime) -> bool:
    previous = last_seen.get(fp)
    if previous and now - previous < DEDUP_WINDOW:
        return True
    last_seen[fp] = now
    return False
