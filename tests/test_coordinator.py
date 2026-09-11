"""Coordinator tests. Equipment names here are arbitrary labels; grouping
never consults the site config, so no real mapping is needed.
"""
from datetime import datetime, timedelta

from gemma_anomaly.contracts.findings import (
    AgentResult, CallStatus, Category, PanelFinding,
)
from gemma_anomaly.coordinator import group

T0 = datetime(2026, 9, 11, 18, 0)


def _finding(panel, category, equipment=None, offset_min=0):
    return PanelFinding(
        panel_id=panel,
        category=category,
        equipment=equipment,
        interval_start=T0 + timedelta(minutes=offset_min),
        interval_end=T0 + timedelta(minutes=offset_min + 5),
        evidence_ids=[],
        evidence_basis="inferred",
        summary="x",
    )


def _result(finding):
    return AgentResult(status=CallStatus.OK, panel_id=finding.panel_id,
                       snapshot_id="snap_test", finding=finding)


def test_same_equipment_nearby_merges():
    a = _finding("panel3", Category.PROLONGED_OPERATION, "pump", 0)
    b = _finding("panel3", Category.PROLONGED_OPERATION, "pump", 6)
    clusters = group.group([_result(a), _result(b)])
    assert len(clusters) == 1


def test_unrelated_findings_stay_apart():
    a = _finding("panel1", Category.UNUSUAL_CYCLING, "fan", 0)
    b = _finding("panel3", Category.UNEXPECTED_DEMAND, "heater", 90)
    clusters = group.group([_result(a), _result(b)])
    assert len(clusters) == 2


def test_incident_id_is_stable_across_retries():
    f = _finding("panel3", Category.PROLONGED_OPERATION, "pump")
    fp = group.fingerprint([f])
    assert group.incident_id(fp, T0) == group.incident_id(fp, T0)


def test_telemetry_problem_outranks_normal():
    findings = [
        _finding("panel1", Category.NORMAL),
        _finding("panel2", Category.TELEMETRY_PROBLEM),
    ]
    assert group.headline(findings) is Category.TELEMETRY_PROBLEM


def test_normal_is_not_actionable():
    assert not group.is_actionable(_finding("panel1", Category.NORMAL))
    assert not group.is_actionable(_finding("panel1", Category.INSUFFICIENT_EVIDENCE))
    assert group.is_actionable(_finding("panel1", Category.UNUSUAL_CYCLING))


def test_duplicate_is_suppressed_within_window():
    seen: dict = {}
    assert group.suppress_duplicate("fp1", seen, T0) is False
    assert group.suppress_duplicate("fp1", seen, T0 + timedelta(minutes=5)) is True
    assert group.suppress_duplicate("fp1", seen, T0 + timedelta(minutes=45)) is False


def test_total_agent_failure_still_produces_an_incident(monkeypatch):
    """A broken endpoint must not read as a quiet house."""
    from gemma_anomaly.coordinator import workflow
    from gemma_anomaly.contracts.snapshot import HouseholdSnapshot

    snap = HouseholdSnapshot(
        snapshot_id="snap_test",
        decision_time=T0,
        window_start=T0 - timedelta(minutes=30),
        window_end=T0,
        site_config_version="test",
    )
    monkeypatch.setattr(workflow, "run_agents", lambda *a, **k: [
        AgentResult(status=CallStatus.TRANSPORT_ERROR, panel_id=p,
                    snapshot_id="snap_test", error="endpoint down")
        for p in ("panel1", "panel2", "panel3")
    ])
    incidents = workflow.assess(snap)
    assert len(incidents) == 1
    assert incidents[0].headline_category is Category.INSUFFICIENT_EVIDENCE
    assert incidents[0].panels_failed == ["panel1", "panel2", "panel3"]
    assert incidents[0].unresolved_questions
