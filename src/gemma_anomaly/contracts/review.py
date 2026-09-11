"""Human review contracts for the Nango Google Sheets round trip."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ReviewVerdict(str, Enum):
    CONFIRMED_ANOMALY = "confirmed_anomaly"
    NORMAL_BEHAVIOR = "normal_behavior"
    WRONG_APPLIANCE = "wrong_appliance"
    TELEMETRY_ISSUE = "telemetry_issue"
    UNSURE = "unsure"


class LabelProvenance(str, Enum):
    VERIFIED = "verified"       # a human confirmed it
    WEAK = "weak"               # produced by the physics rules layer
    SYNTHETIC = "synthetic"     # injected for demonstration or training


class ReviewRow(BaseModel):
    """One row exported to the sheet. Keyed by incident_id so retries update it."""
    incident_id: str
    trace_url: str | None = None
    dashboard_url: str | None = None
    proposed_equipment: str | None = None
    proposed_category: str | None = None
    evidence_summary: str = ""
    interval_start: datetime
    interval_end: datetime
    mode: str = "live"
    exported_at: datetime


class ReviewOutcome(BaseModel):
    """One completed review imported back. Appended, never overwriting the proposal."""
    incident_id: str
    appliance_confirmed: bool | None = Field(
        default=None,
        description="Separate from anomaly_confirmed. A confirmed pump run is not an abnormal pump run.",
    )
    anomaly_confirmed: bool | None = None
    verdict: ReviewVerdict
    corrected_equipment: str | None = None
    corrected_category: str | None = None
    reviewer: str
    reviewed_at: datetime
    explanation: str | None = None
    provenance: LabelProvenance = LabelProvenance.VERIFIED
    revision: int = Field(default=1, description="Increments, never replaces a prior revision.")
