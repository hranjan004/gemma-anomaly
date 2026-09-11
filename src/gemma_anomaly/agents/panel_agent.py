"""One panel agent.

Three logical agents, one shared adapter conditioned on panel identity. Three
agents do not require three GPUs or three copies of the base model. Separately
trained per panel adapters remain an optional experiment.
"""
from __future__ import annotations

from ..contracts.findings import AgentResult, CallStatus
from ..contracts.snapshot import HouseholdSnapshot
from ..serving import respan
from ..serving.client import Route, ServingError, base_route, complete
from . import parser, prompts


def assess(snap: HouseholdSnapshot, panel_id: str, route: Route | None = None,
           incident_id: str | None = None, timeout: int = 45) -> AgentResult:
    route = route or base_route()
    messages = prompts.build_messages(snap, panel_id)
    headers, trace_id = respan.trace_headers(
        snapshot_id=snap.snapshot_id,
        panel_id=panel_id,
        prompt_version=prompts.PROMPT_VERSION,
        route_name=route.name,
        model=route.model,
        adapter=route.adapter,
        incident_id=incident_id,
    )

    common = dict(
        panel_id=panel_id,
        snapshot_id=snap.snapshot_id,
        model_id=route.model,
        adapter_id=route.adapter,
        prompt_version=prompts.PROMPT_VERSION,
        trace_id=trace_id,
    )

    try:
        raw, latency_ms = complete(messages, route, timeout=timeout,
                                   extra_headers=headers)
    except ServingError as exc:
        status = (CallStatus.TIMEOUT if "timed out" in str(exc).lower()
                  else CallStatus.TRANSPORT_ERROR)
        return AgentResult(status=status, error=str(exc), **common)

    try:
        finding = parser.parse(
            raw,
            panel_id,
            prompts.valid_evidence_ids(snap, panel_id),
            snap.window_start,
            snap.window_end,
        )
    except parser.ParseError as exc:
        return AgentResult(status=CallStatus.INVALID_OUTPUT, raw_output=raw,
                           error=str(exc), latency_ms=latency_ms, **common)

    return AgentResult(status=CallStatus.OK, finding=finding, raw_output=raw,
                       latency_ms=latency_ms, **common)
