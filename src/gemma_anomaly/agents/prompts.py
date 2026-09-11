"""Versioned prompt templates.

PROMPT_VERSION is attached to every trace. Change the string whenever the text
changes, otherwise two runs are not comparable.
"""
from __future__ import annotations

import json

from ..contracts.snapshot import HouseholdSnapshot, PanelView
from ..settings import site

PROMPT_VERSION = "panel-v0.1"

SYSTEM = """You assess one electrical panel in a residential microgrid.

You receive a household snapshot and one panel's evidence. Decide whether the
panel's recent behavior is normal or anomalous.

Rules you must follow.
1. Answer with one JSON object and nothing else.
2. category must be one of: normal, prolonged_operation, unusual_cycling,
   unexpected_demand, telemetry_problem, insufficient_evidence.
3. equipment must be an appliance listed for this panel, or null.
4. Every id in evidence_ids must appear in the evidence you were given.
5. Never output a numeric confidence or probability.
6. A measured appliance state is stronger evidence than an inferred estimate.
   Say which you relied on in evidence_basis.
7. A fall in solar generation raises grid import without any appliance anomaly.
8. If the evidence cannot support a decision, answer insufficient_evidence and
   put one specific request in follow_up.

Output schema.
{"category": str, "equipment": str|null, "interval_start": iso8601,
 "interval_end": iso8601, "evidence_ids": [str], "evidence_basis": str,
 "follow_up": str|null, "summary": str}
"""


def _panel_payload(snap: HouseholdSnapshot, view: PanelView) -> dict:
    cfg = site()["panels"][view.panel_id]
    return {
        "panel_id": view.panel_id,
        "channel": view.channel,
        "focus": cfg["focus"],
        "appliances_on_this_panel": cfg["appliances"],
        "measured_heads": cfg["measured_heads"],
        "panel_w": view.panel_w,
        "freshness": view.freshness.model_dump() if view.freshness else None,
        "appliance_estimates": [a.model_dump(mode="json") for a in view.appliances],
        "derived": {k: v.model_dump() for k, v in view.derived.items()},
        "equipment_context": [e.model_dump(mode="json") for e in view.equipment],
        "recent_panel_w": [[s.ts.isoformat(), s.w] for s in view.recent],
        "evidence": [
            {"id": e.id, "kind": e.kind.value, "label": e.label, "value": e.value,
             "unit": e.unit, "source": e.source, "note": e.note}
            for e in view.evidence
        ],
    }


def _household_payload(snap: HouseholdSnapshot) -> dict:
    return {
        "decision_time": snap.decision_time.isoformat(),
        "window_start": snap.window_start.isoformat(),
        "window_end": snap.window_end.isoformat(),
        "mode": snap.mode,
        "grid_w": snap.grid_w,
        "generac_w": snap.generac_w,
        "shop_w": snap.shop_w,
        "solar": snap.solar.model_dump(mode="json") if snap.solar else None,
        "data_quality": [
            {"id": e.id, "value": e.value,
             "freshness": e.freshness.model_dump() if e.freshness else None}
            for e in snap.data_quality
        ],
        "note": "Main meter and subpanel channels overlap. Never add them as independent loads.",
    }


def build_messages(snap: HouseholdSnapshot, panel_id: str) -> list[dict]:
    view = snap.panels[panel_id]
    user = {
        "household": _household_payload(snap),
        "panel": _panel_payload(snap, view),
        "categories": list(site().get("categories", []) or []),
    }
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps(user, separators=(",", ":"), default=str)},
    ]


def valid_evidence_ids(snap: HouseholdSnapshot, panel_id: str) -> set[str]:
    ids = {e.id for e in snap.panels[panel_id].evidence}
    ids |= {e.id for e in snap.data_quality}
    return ids
