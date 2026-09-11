"""Dataset assembly.

Chronological train, validation, and test partitions are cut BEFORE windows are
overlapped. Every window from one physical incident stays on the same side of a
boundary, and lookback history is accounted for so no test context leaks into
training. Baselines and normalization are fit on training periods only.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .labels import Label

LOOKBACK = timedelta(minutes=30)


@dataclass
class Example:
    snapshot_id: str
    panel_id: str
    prompt: str
    completion: str
    incident_id: str | None
    provenance: str
    decision_time: str


@dataclass
class Split:
    train: list[Example]
    val: list[Example]
    test: list[Example]

    def manifest(self) -> dict:
        return {
            "counts": {"train": len(self.train), "val": len(self.val),
                       "test": len(self.test)},
            "provenance": {
                name: _count_provenance(getattr(self, name))
                for name in ("train", "val", "test")
            },
        }


def _count_provenance(rows: list[Example]) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        out[r.provenance] = out.get(r.provenance, 0) + 1
    return out


def chronological_split(examples: list[Example], labels: list[Label],
                        val_fraction: float = 0.15,
                        test_fraction: float = 0.15) -> Split:
    rows = sorted(examples, key=lambda e: e.decision_time)
    n = len(rows)
    test_start = int(n * (1 - test_fraction))
    val_start = int(n * (1 - test_fraction - val_fraction))

    incident_of = {l.incident_id: l for l in labels}

    def boundary_safe(idx: int) -> int:
        """Walk the boundary back until it does not split an incident, and until
        the lookback of the first held out example does not reach training."""
        while idx > 0 and rows[idx].incident_id and \
                rows[idx].incident_id == rows[idx - 1].incident_id:
            idx -= 1
        if idx > 0:
            cutoff = datetime.fromisoformat(rows[idx].decision_time) - LOOKBACK
            while idx > 0 and datetime.fromisoformat(rows[idx - 1].decision_time) > cutoff:
                idx -= 1
        return idx

    val_start = boundary_safe(val_start)
    test_start = boundary_safe(test_start)

    _ = incident_of  # kept for future per incident stratification
    return Split(train=rows[:val_start], val=rows[val_start:test_start],
                 test=rows[test_start:])


def write_jsonl(rows: list[Example], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(asdict(r)) + "\n")
    return out


def sanity_checks(split: Split) -> list[str]:
    """Returns a list of problems. An empty list is the only acceptable result."""
    problems: list[str] = []
    ids = {name: {e.incident_id for e in getattr(split, name) if e.incident_id}
           for name in ("train", "val", "test")}
    for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
        shared = ids[a] & ids[b]
        if shared:
            problems.append(f"incidents shared between {a} and {b}: {sorted(shared)[:5]}")
    if not any(e.provenance == "verified" for e in split.test):
        problems.append("test set has no verified labels, results would not be trustworthy")
    normals = sum(1 for e in split.train if '"normal"' in e.completion)
    if normals == 0:
        problems.append("training set has no normal examples, it cannot teach normal vs abnormal")
    return problems
