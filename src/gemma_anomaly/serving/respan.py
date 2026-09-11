"""Respan trace attachment.

Every model call carries snapshot id, panel id, model and adapter version,
prompt version, and incident id, so an alert can be traced back to its exact
input. Self hosted GPU cost is not in the token log and must be allocated
separately.
"""
from __future__ import annotations

import uuid

from .. import settings


def trace_headers(*, snapshot_id: str, panel_id: str, prompt_version: str,
                  route_name: str, model: str, adapter: str | None,
                  incident_id: str | None = None) -> tuple[dict, str]:
    trace_id = f"tr_{uuid.uuid4().hex[:16]}"
    headers = {
        "X-Respan-Trace-Id": trace_id,
        "X-Respan-Snapshot-Id": snapshot_id,
        "X-Respan-Panel-Id": panel_id,
        "X-Respan-Prompt-Version": prompt_version,
        "X-Respan-Route": route_name,
        "X-Respan-Model": model,
        "X-Respan-Adapter": adapter or "none",
    }
    if incident_id:
        headers["X-Respan-Incident-Id"] = incident_id
    if settings.RESPAN_API_KEY:
        headers["Authorization"] = f"Bearer {settings.RESPAN_API_KEY}"
    return headers, trace_id


def trace_url(trace_id: str) -> str | None:
    if not settings.RESPAN_BASE_URL:
        return None
    return f"{settings.RESPAN_BASE_URL.rstrip('/')}/traces/{trace_id}"
