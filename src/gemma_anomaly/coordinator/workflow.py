"""The assessment workflow.

1. Build one immutable household snapshot and three panel views.
2. Run the three panel agents independently.
3. Validate responses and preserve partial failures.
4. Group related findings, retaining links to all originals.
5. Ask for at most one targeted follow up per affected panel.
6. Present an incident separating measured from inferred evidence.
7. Export the incident for review.

There is no agent to agent discussion. Another agent's output is supporting
inference, never ground truth. If coordination fails, the original panel
findings are still shown with a coordination_error set.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from ..contracts.findings import AgentResult, CallStatus, Category, Incident
from ..contracts.snapshot import EvidenceKind, HouseholdSnapshot
from ..agents import panel_agent
from ..serving.client import Route, base_route
from ..snapshot.builder import PANEL_IDS
from . import group as grouping

log = logging.getLogger(__name__)

MAX_FOLLOW_UPS_PER_PANEL = 1


def run_agents(snap: HouseholdSnapshot, route: Route | None = None,
               timeout: int = 45) -> list[AgentResult]:
    route = route or base_route()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(panel_agent.assess, snap, pid, route, None, timeout)
            for pid in PANEL_IDS
        ]
        return [f.result() for f in futures]


def _split_evidence(snap: HouseholdSnapshot, evidence_ids: list[str]
                    ) -> tuple[list[str], list[str]]:
    kinds: dict[str, EvidenceKind] = {}
    for view in snap.panels.values():
        kinds.update({e.id: e.kind for e in view.evidence})
    kinds.update({e.id: e.kind for e in snap.data_quality})

    measured = [i for i in evidence_ids
                if kinds.get(i) in (EvidenceKind.MEASURED, EvidenceKind.EXTERNAL)]
    inferred = [i for i in evidence_ids
                if kinds.get(i) in (EvidenceKind.INFERRED, EvidenceKind.RULE,
                                    EvidenceKind.DERIVED)]
    return measured, inferred


def assess(snap: HouseholdSnapshot, route: Route | None = None,
           timeout: int = 45) -> list[Incident]:
    results = run_agents(snap, route, timeout)

    ok = [r for r in results if r.status is CallStatus.OK and r.finding]
    failed = [r for r in results if r.status is not CallStatus.OK]

    try:
        clusters = grouping.group(ok)
        coordination_error = None
    except Exception as exc:                       # never lose alerts
        log.exception("coordination failed")
        clusters = [[r.finding] for r in ok if r.finding]
        coordination_error = str(exc)

    incidents: list[Incident] = []

    if not clusters and failed:
        # Every agent failed. The failure is itself the result and must not be
        # dropped, otherwise a broken endpoint reads as a quiet house.
        fp = "allfail:" + ",".join(sorted(r.panel_id for r in failed))
        incidents.append(Incident(
            incident_id=grouping.incident_id(fp, snap.decision_time),
            snapshot_id=snap.snapshot_id,
            decision_time=snap.decision_time,
            interval_start=snap.window_start,
            interval_end=snap.window_end,
            panels_reporting=[],
            panels_failed=[r.panel_id for r in failed],
            headline_category=Category.INSUFFICIENT_EVIDENCE,
            equipment=[],
            findings=[],
            agent_results=results,
            measured_evidence_ids=[],
            inferred_evidence_ids=[],
            unresolved_questions=[
                f"{r.panel_id} returned no usable answer: {r.status.value} {r.error or ''}".strip()
                for r in failed
            ],
            coordination_error=coordination_error,
            mode=snap.mode,
            fingerprint=fp,
        ))
        return incidents

    for findings in clusters:
        fp = grouping.fingerprint(findings)
        start = min(f.interval_start for f in findings)
        end = max(f.interval_end for f in findings)

        evidence_ids = [i for f in findings for i in f.evidence_ids]
        measured, inferred = _split_evidence(snap, evidence_ids)

        questions = [f.follow_up for f in findings if f.follow_up][
            : MAX_FOLLOW_UPS_PER_PANEL * len(findings)
        ]
        questions += [
            f"{r.panel_id} did not return a usable answer: {r.status.value}"
            for r in failed
        ]

        incidents.append(Incident(
            incident_id=grouping.incident_id(fp, start),
            snapshot_id=snap.snapshot_id,
            decision_time=snap.decision_time,
            interval_start=start,
            interval_end=end,
            panels_reporting=[f.panel_id for f in findings],
            panels_failed=[r.panel_id for r in failed],
            headline_category=grouping.headline(findings),
            equipment=sorted({f.equipment for f in findings if f.equipment}),
            findings=findings,
            agent_results=results,
            measured_evidence_ids=sorted(set(measured)),
            inferred_evidence_ids=sorted(set(inferred)),
            unresolved_questions=questions,
            coordination_error=coordination_error,
            mode=snap.mode,
            fingerprint=fp,
        ))

    return incidents


def actionable(incidents: list[Incident]) -> list[Incident]:
    return [i for i in incidents
            if any(grouping.is_actionable(f) for f in i.findings)]
