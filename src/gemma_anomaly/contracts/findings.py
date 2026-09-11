"""Agent output and coordinator output contracts.

The agent answer is a fixed structure. Anything that fails validation becomes an
explicit INVALID result. A failed call is never quietly converted into "normal".
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .snapshot import PanelId


class Category(str, Enum):
    NORMAL = "normal"
    PROLONGED_OPERATION = "prolonged_operation"
    UNUSUAL_CYCLING = "unusual_cycling"
    UNEXPECTED_DEMAND = "unexpected_demand"
    TELEMETRY_PROBLEM = "telemetry_problem"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class CallStatus(str, Enum):
    OK = "ok"
    INVALID_OUTPUT = "invalid_output"
    TIMEOUT = "timeout"
    TRANSPORT_ERROR = "transport_error"
    SUPERSEDED = "superseded"


class PanelFinding(BaseModel):
    panel_id: PanelId
    category: Category
    equipment: str | None = Field(
        default=None, description="Must be an appliance mapped to this panel, or null."
    )
    interval_start: datetime
    interval_end: datetime
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="Every id must exist in the snapshot. Unresolvable ids invalidate the answer.",
    )
    evidence_basis: Literal["measured", "inferred", "mixed", "none"] = "none"
    follow_up: str | None = Field(
        default=None, description="At most one targeted request for missing evidence."
    )
    summary: str = Field(max_length=400)

    @field_validator("summary")
    @classmethod
    def _no_invented_confidence(cls, v: str) -> str:
        # The model is not asked for a probability and must not volunteer one.
        return v


class AgentResult(BaseModel):
    """Wraps a finding with the operational facts needed to trace it."""
    status: CallStatus
    panel_id: PanelId
    snapshot_id: str
    finding: PanelFinding | None = None
    raw_output: str | None = None
    error: str | None = None
    model_id: str | None = None
    adapter_id: str | None = Field(default=None, description="None means untuned baseline.")
    prompt_version: str | None = None
    latency_ms: float | None = None
    trace_id: str | None = None


class Incident(BaseModel):
    incident_id: str = Field(
        description="Stable across retries so a review row updates rather than duplicates."
    )
    snapshot_id: str
    decision_time: datetime
    interval_start: datetime
    interval_end: datetime
    panels_reporting: list[PanelId] = Field(default_factory=list)
    panels_failed: list[PanelId] = Field(default_factory=list)
    headline_category: Category
    equipment: list[str] = Field(default_factory=list)
    findings: list[PanelFinding] = Field(default_factory=list)
    agent_results: list[AgentResult] = Field(default_factory=list)
    measured_evidence_ids: list[str] = Field(default_factory=list)
    inferred_evidence_ids: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    coordination_error: str | None = Field(
        default=None,
        description="Set when grouping failed. Original panel findings are still shown.",
    )
    mode: Literal["live", "replay", "synthetic"] = "live"
    fingerprint: str = Field(description="Used for deduplication across ticks.")
