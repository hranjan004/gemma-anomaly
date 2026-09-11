"""Immutable evidence contracts.

A snapshot is built once per assessment tick and never mutated afterwards.
Every panel agent sees the same household context and only its own panel view.
Measured values, model estimates, and derived features stay in separate fields
so a downstream reader can always tell which is which.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

PanelId = Literal["panel1", "panel2", "panel3"]


class EvidenceKind(str, Enum):
    MEASURED = "measured"          # a dedicated CT or sensor channel
    INFERRED = "inferred"          # BiLSTM head output
    RULE = "rule"                  # physics rules layer
    DERIVED = "derived"            # computed in ordinary code from the above
    EXTERNAL = "external"          # Home Assistant or another system


class Freshness(BaseModel):
    age_s: float
    expected_period_s: float
    stale: bool
    gap_count: int = 0
    frozen: bool = False


class EvidenceItem(BaseModel):
    """One citable fact. Agents may only reference evidence by its id."""
    id: str = Field(description="Stable within a snapshot, e.g. panel3.<appliance>.state")
    kind: EvidenceKind
    label: str
    value: float | int | str | bool | None
    unit: str | None = None
    source: str = Field(description="Table, channel, model artifact, or entity id")
    at: datetime
    freshness: Freshness | None = None
    note: str | None = None


class PowerSample(BaseModel):
    ts: datetime
    w: float


class ApplianceEstimate(BaseModel):
    appliance: str
    state: Literal["on", "off", "unknown"]
    confidence: float | None = Field(
        default=None,
        description="Model score. NOT calibrated probability. Do not report as certainty.",
    )
    avg_w: float | None = None
    median_w: float | None = None
    std_w: float | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    measured: bool = Field(
        default=False,
        description="True only for heads with a genuine independent measurement channel.",
    )
    rule_agrees: bool | None = Field(
        default=None,
        description="Rules layer agreement. Not independent confirmation, the rules generated the labels.",
    )


class DerivedFeatures(BaseModel):
    """Computed in ordinary code, never asked of the model."""
    run_duration_s: float | None = None
    switch_count: int | None = None
    switches_per_h: float | None = None
    energy_wh: float | None = None
    baseline_w: float | None = None
    deviation_sigma: float | None = None
    duty_cycle: float | None = None


class SolarContext(BaseModel):
    pv_power: float | None = None
    battery_power: float | None = None
    battery_soc: float | None = None
    grid_power: float | None = None
    load_power: float | None = None
    device_mode: str | None = None
    freshness: Freshness | None = None


class EquipmentContext(BaseModel):
    """Home Assistant. A commanded state is not proof of physical operation."""
    entity_id: str
    state: str | None
    commanded: bool = Field(
        default=False,
        description="True when this reflects a setpoint or command, not an observation.",
    )
    available: bool = True
    at: datetime | None = None


class PanelView(BaseModel):
    panel_id: PanelId
    channel: str
    label: str
    panel_w: float | None
    recent: list[PowerSample] = Field(
        default_factory=list,
        description="Compact downsampled sequence, not the full archive.",
    )
    appliances: list[ApplianceEstimate] = Field(default_factory=list)
    derived: dict[str, DerivedFeatures] = Field(
        default_factory=dict, description="Keyed by appliance name."
    )
    equipment: list[EquipmentContext] = Field(default_factory=list)
    freshness: Freshness | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)


class HouseholdSnapshot(BaseModel):
    """The single immutable input to one assessment tick."""
    snapshot_id: str
    decision_time: datetime = Field(
        description="Simulated or live. Nothing measured after this time may appear anywhere below."
    )
    window_start: datetime
    window_end: datetime
    site_config_version: str
    grid_w: float | None = None
    generac_w: float | None = None
    shop_w: float | None = None
    solar: SolarContext | None = None
    panels: dict[PanelId, PanelView] = Field(default_factory=dict)
    data_quality: list[EvidenceItem] = Field(default_factory=list)
    mode: Literal["live", "replay", "synthetic"] = "live"

    model_config = {"frozen": True}
