"""Strict validation of a model answer.

An answer that does not validate becomes INVALID_OUTPUT. It never becomes
"normal" and it never falls back to another model.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from ..contracts.findings import Category, PanelFinding
from ..settings import site

_JSON = re.compile(r"\{.*\}", re.S)
_NUMBER_CLAIM = re.compile(
    r"\b(\d{1,3}(\.\d+)?\s*%|confidence\s*[:=]\s*\d|probability\s*[:=]\s*\d)", re.I
)


class ParseError(ValueError):
    pass


def parse(raw: str, panel_id: str, allowed_ids: set[str],
          fallback_start: datetime, fallback_end: datetime) -> PanelFinding:
    match = _JSON.search(raw or "")
    if not match:
        raise ParseError("no JSON object in output")
    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ParseError(f"malformed JSON: {exc}") from exc

    try:
        category = Category(str(obj.get("category", "")).strip())
    except ValueError as exc:
        raise ParseError(f"unknown category {obj.get('category')!r}") from exc

    equipment = obj.get("equipment")
    if equipment is not None:
        allowed = site()["panels"][panel_id]["appliances"]
        if equipment not in allowed:
            raise ParseError(f"{equipment!r} is not an appliance on {panel_id}")

    ids = obj.get("evidence_ids") or []
    if not isinstance(ids, list):
        raise ParseError("evidence_ids must be a list")
    unknown = [i for i in ids if i not in allowed_ids]
    if unknown:
        raise ParseError(f"evidence ids not in snapshot: {unknown[:4]}")

    summary = str(obj.get("summary", "")).strip()
    if _NUMBER_CLAIM.search(summary):
        raise ParseError("summary asserts a confidence or probability")

    def _ts(key: str, default: datetime) -> datetime:
        val = obj.get(key)
        if not val:
            return default
        try:
            return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ParseError(f"bad timestamp for {key}") from exc

    basis = str(obj.get("evidence_basis", "none")).strip()
    if basis not in {"measured", "inferred", "mixed", "none"}:
        basis = "none"

    return PanelFinding(
        panel_id=panel_id,
        category=category,
        equipment=equipment,
        interval_start=_ts("interval_start", fallback_start),
        interval_end=_ts("interval_end", fallback_end),
        evidence_ids=ids,
        evidence_basis=basis,
        follow_up=obj.get("follow_up") or None,
        summary=summary[:400],
    )
