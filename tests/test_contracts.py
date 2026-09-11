"""Contract tests.

These assert invariants that must hold for ANY site configuration, so they pass
against config/site.example.yaml and against a real local config/site.yaml
alike. Nothing here hardcodes a particular building's appliance mapping.
"""
import json
from datetime import datetime, timedelta

import pytest

from gemma_anomaly.agents import parser
from gemma_anomaly.contracts.findings import Category
from gemma_anomaly.settings import is_measured, panel_for_appliance, site

T0 = datetime(2026, 1, 1, 12, 0)
T1 = T0 + timedelta(minutes=30)


@pytest.fixture(scope="module")
def panel_and_appliance():
    """A panel id and one appliance that belongs to it, from the live config."""
    for pid, cfg in site()["panels"].items():
        if cfg["appliances"]:
            return pid, cfg["appliances"][0]
    pytest.skip("site config has no appliances")


@pytest.fixture(scope="module")
def foreign_appliance(panel_and_appliance):
    """An appliance that belongs to some OTHER panel."""
    pid, _ = panel_and_appliance
    for other, cfg in site()["panels"].items():
        if other != pid and cfg["appliances"]:
            return cfg["appliances"][0]
    pytest.skip("site config has only one populated panel")


def _raw(panel_and_appliance, **over):
    _, appliance = panel_and_appliance
    obj = {
        "category": "prolonged_operation",
        "equipment": appliance,
        "interval_start": T0.isoformat(),
        "interval_end": T1.isoformat(),
        "evidence_ids": ["ev.a"],
        "evidence_basis": "inferred",
        "follow_up": None,
        "summary": "Equipment has run continuously for most of the window.",
    }
    obj.update(over)
    return json.dumps(obj)


# -- site config invariants -------------------------------------------------

def test_every_appliance_maps_to_exactly_one_panel():
    seen: dict[str, str] = {}
    for pid, cfg in site()["panels"].items():
        for appliance in cfg["appliances"]:
            assert appliance not in seen, (
                f"{appliance} is on both {seen[appliance]} and {pid}"
            )
            seen[appliance] = pid
            assert panel_for_appliance(appliance) == pid


def test_measured_heads_belong_to_their_own_panel():
    for pid, cfg in site()["panels"].items():
        for head in cfg["measured_heads"]:
            assert head in cfg["appliances"], f"{head} is not an appliance on {pid}"
            assert is_measured(head), f"{head} is not listed in evidence_quality.measured"


def test_measured_list_matches_the_panel_declarations():
    declared = {h for cfg in site()["panels"].values() for h in cfg["measured_heads"]}
    assert set(site()["evidence_quality"]["measured"]) == declared


def test_every_panel_channel_appears_in_the_channel_list():
    channels = set(site()["channels"]["panels"])
    for pid, cfg in site()["panels"].items():
        assert cfg["channel"] in channels, f"{pid} channel is not in channels.panels"


def test_model_contract_window_is_internally_consistent():
    mc = site()["model_contract"]
    assert 0 < mc["mid"] < mc["window"]
    assert 0 < mc["stride"] <= mc["window"]
    assert mc["features"] > 0


# -- parser invariants ------------------------------------------------------

def test_valid_answer_parses(panel_and_appliance):
    pid, appliance = panel_and_appliance
    f = parser.parse(_raw(panel_and_appliance), pid, {"ev.a"}, T0, T1)
    assert f.category is Category.PROLONGED_OPERATION
    assert f.equipment == appliance


def test_appliance_from_another_panel_is_rejected(panel_and_appliance, foreign_appliance):
    pid, _ = panel_and_appliance
    with pytest.raises(parser.ParseError):
        parser.parse(_raw(panel_and_appliance, equipment=foreign_appliance),
                     pid, {"ev.a"}, T0, T1)


def test_unknown_evidence_id_is_rejected(panel_and_appliance):
    pid, _ = panel_and_appliance
    with pytest.raises(parser.ParseError):
        parser.parse(_raw(panel_and_appliance, evidence_ids=["ev.made_up"]),
                     pid, {"ev.a"}, T0, T1)


def test_invented_confidence_is_rejected(panel_and_appliance):
    pid, _ = panel_and_appliance
    with pytest.raises(parser.ParseError):
        parser.parse(_raw(panel_and_appliance, summary="Anomalous, confidence: 0.92"),
                     pid, {"ev.a"}, T0, T1)


def test_unknown_category_is_rejected(panel_and_appliance):
    pid, _ = panel_and_appliance
    with pytest.raises(parser.ParseError):
        parser.parse(_raw(panel_and_appliance, category="catastrophe"),
                     pid, {"ev.a"}, T0, T1)


def test_non_json_output_is_rejected(panel_and_appliance):
    pid, _ = panel_and_appliance
    with pytest.raises(parser.ParseError):
        parser.parse("the panel looks fine to me", pid, {"ev.a"}, T0, T1)


def test_null_equipment_is_allowed(panel_and_appliance):
    pid, _ = panel_and_appliance
    f = parser.parse(_raw(panel_and_appliance, equipment=None, category="telemetry_problem"),
                     pid, {"ev.a"}, T0, T1)
    assert f.equipment is None
    assert f.category is Category.TELEMETRY_PROBLEM
