"""Nango backed Google Sheets review loop.

Nango supplies the integration layer. Incident selection, row mapping,
reconciliation, and validation are ours. Rows are keyed by incident_id so a
retry updates the same row instead of producing a duplicate, and an imported
correction is appended as a new revision rather than overwriting the proposal.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime

from .. import settings
from ..contracts.findings import Incident
from ..contracts.review import ReviewOutcome, ReviewRow, ReviewVerdict
from ..serving.respan import trace_url

HEADERS = [
    "incident_id", "exported_at", "interval_start", "interval_end", "mode",
    "proposed_equipment", "proposed_category", "evidence_summary",
    "trace_url", "dashboard_url",
    "appliance_confirmed", "anomaly_confirmed", "verdict",
    "corrected_equipment", "corrected_category", "reviewer", "reviewed_at",
    "explanation",
]


def to_row(inc: Incident, dashboard_base: str = "") -> ReviewRow:
    trace = next((r.trace_id for r in inc.agent_results if r.trace_id), None)
    summary_parts = [
        f"{f.panel_id} {f.category.value} {f.equipment or ''}: {f.summary}"
        for f in inc.findings
    ]
    if inc.panels_failed:
        summary_parts.append(f"panels without a usable answer: {', '.join(inc.panels_failed)}")
    summary_parts.append(
        f"measured evidence {len(inc.measured_evidence_ids)}, "
        f"inferred evidence {len(inc.inferred_evidence_ids)}"
    )
    return ReviewRow(
        incident_id=inc.incident_id,
        trace_url=trace_url(trace) if trace else None,
        dashboard_url=(f"{dashboard_base.rstrip('/')}/incident/{inc.incident_id}"
                       if dashboard_base else None),
        proposed_equipment=inc.equipment[0] if inc.equipment else None,
        proposed_category=inc.headline_category.value,
        evidence_summary=" | ".join(summary_parts)[:1000],
        interval_start=inc.interval_start,
        interval_end=inc.interval_end,
        mode=inc.mode,
        exported_at=datetime.now(),
    )


def _nango(path: str, method: str = "GET", body: dict | None = None) -> dict:
    if not settings.NANGO_SECRET_KEY:
        raise RuntimeError("NANGO_SECRET_KEY is unset")
    req = urllib.request.Request(
        f"{settings.NANGO_BASE_URL.rstrip('/')}{path}",
        method=method,
        data=json.dumps(body).encode() if body else None,
        headers={
            "Authorization": f"Bearer {settings.NANGO_SECRET_KEY}",
            "Connection-Id": settings.NANGO_CONNECTION_ID,
            "Provider-Config-Key": "google-sheet",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def export_incident(inc: Incident, dashboard_base: str = "") -> ReviewRow:
    """Upsert one review row. Implemented against the Nango Google Sheets proxy.

    Left unimplemented until the connection is created, because the exact proxy
    path depends on the integration configured in the Nango dashboard.
    """
    row = to_row(inc, dashboard_base)
    raise NotImplementedError(
        "Create the Nango Google Sheets connection, then upsert by matching "
        f"column A to incident_id. Row payload is ready: {row.incident_id}"
    )


def import_reviews(since: datetime | None = None) -> list[ReviewOutcome]:
    """Import only completed, validated reviews. A blank verdict is skipped."""
    raise NotImplementedError(
        "Read the sheet through the Nango proxy, drop rows with an empty "
        "verdict, validate corrected_equipment against config/site.yaml, and "
        "return one ReviewOutcome per completed row."
    )


def validate_outcome(raw: dict) -> ReviewOutcome | None:
    verdict = str(raw.get("verdict", "")).strip()
    if not verdict:
        return None
    try:
        parsed = ReviewVerdict(verdict)
    except ValueError:
        return None
    reviewed_at = raw.get("reviewed_at")
    return ReviewOutcome(
        incident_id=str(raw["incident_id"]).strip(),
        appliance_confirmed=_tri(raw.get("appliance_confirmed")),
        anomaly_confirmed=_tri(raw.get("anomaly_confirmed")),
        verdict=parsed,
        corrected_equipment=(raw.get("corrected_equipment") or None),
        corrected_category=(raw.get("corrected_category") or None),
        reviewer=str(raw.get("reviewer", "")).strip() or "unknown",
        reviewed_at=datetime.fromisoformat(reviewed_at) if reviewed_at else datetime.now(),
        explanation=raw.get("explanation") or None,
    )


def _tri(value) -> bool | None:
    if value in (None, "", "unsure"):
        return None
    return str(value).strip().lower() in {"true", "yes", "y", "1"}
