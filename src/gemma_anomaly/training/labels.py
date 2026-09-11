"""Label provenance and bootstrap.

A detection system is usually built before anyone has labeled anything, so
assume there is no curated anomaly history. The initial label set comes from
replaying a rules-based detector over the historical archive and having a human
review its output, with provenance kept separate at every stage.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..contracts.findings import Category
from ..contracts.review import LabelProvenance


@dataclass
class Label:
    incident_id: str
    snapshot_id: str
    panel_id: str
    start: datetime
    end: datetime
    category: Category
    equipment: str | None
    provenance: LabelProvenance
    reviewer: str | None = None
    revision: int = 1
    superseded_by: str | None = None


def inventory(labels: list[Label]) -> dict:
    """Count reviewed incidents, reviewed normal periods, weak and synthetic
    examples, by category and panel. Run this before training anything. A model
    cannot learn a category from a convincing demo alone."""
    out: dict[str, dict] = {}
    for lab in labels:
        bucket = out.setdefault(lab.panel_id, {})
        key = f"{lab.category.value}/{lab.provenance.value}"
        bucket[key] = bucket.get(key, 0) + 1
    return out


def trainable(labels: list[Label], allow_synthetic: bool = False) -> list[Label]:
    ok = {LabelProvenance.VERIFIED, LabelProvenance.WEAK}
    if allow_synthetic:
        ok.add(LabelProvenance.SYNTHETIC)
    return [l for l in labels if l.provenance in ok and l.superseded_by is None]


def revise(existing: Label, corrected_category: Category | None,
           corrected_equipment: str | None, reviewer: str) -> Label:
    """Append a revision. The original proposal is never overwritten."""
    return Label(
        incident_id=existing.incident_id,
        snapshot_id=existing.snapshot_id,
        panel_id=existing.panel_id,
        start=existing.start,
        end=existing.end,
        category=corrected_category or existing.category,
        equipment=corrected_equipment or existing.equipment,
        provenance=LabelProvenance.VERIFIED,
        reviewer=reviewer,
        revision=existing.revision + 1,
    )
