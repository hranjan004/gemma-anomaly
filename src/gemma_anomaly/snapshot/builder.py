"""Builds one immutable household snapshot and three panel views.

As-of discipline: nothing measured after decision_time enters the snapshot, and
a carried forward value is dropped once it exceeds max_carry_forward_s. A future
solar reading is never joined into an earlier power window.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from ..contracts.snapshot import (
    ApplianceEstimate,
    EvidenceItem,
    EvidenceKind,
    HouseholdSnapshot,
    PanelView,
    PowerSample,
    SolarContext,
)
from ..evidence import anylog, features, quality
from ..settings import is_measured, site

PANEL_IDS = ("panel1", "panel2", "panel3")


def snapshot_id(decision_time: datetime, window_s: int, mode: str) -> str:
    raw = f"{decision_time.isoformat()}|{window_s}|{mode}"
    return "snap_" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build(decision_time: datetime | None = None, window_minutes: int = 30,
          mode: str = "live", ha_entities: dict[str, list[str]] | None = None
          ) -> HouseholdSnapshot:
    cfg = site()
    if decision_time is None:
        decision_time = anylog.latest_timestamp("power") or datetime.now()
    window_start = decision_time - timedelta(minutes=window_minutes)

    channels = (cfg["channels"]["panels"] + cfg["channels"]["aggregate"])
    power = anylog.get_panel_window(channels, window_start, decision_time)
    solar_rows = anylog.get_solar_snapshot(window_start, decision_time)
    dq_rows = anylog.get_data_quality(window_start, decision_time)

    panels: dict[str, PanelView] = {}
    for pid in PANEL_IDS:
        pcfg = cfg["panels"][pid]
        channel = pcfg["channel"]
        rows = power.get(channel, [])
        est_rows = anylog.get_appliance_estimates(channel, window_start, decision_time)

        baseline = features.hour_baseline(rows, decision_time)
        last_w = _to_float(rows[-1]["w"]) if rows else None

        estimates: list[ApplianceEstimate] = []
        derived: dict = {}
        evidence: list[EvidenceItem] = []

        for appliance in pcfg["appliances"]:
            mine = [r for r in est_rows if r.get("appliance") == appliance]
            latest = mine[-1] if mine else None
            state = "unknown"
            if latest is not None:
                state = "on" if str(latest.get("state", "")).lower().strip() == "on" else "off"

            estimates.append(ApplianceEstimate(
                appliance=appliance,
                state=state,
                confidence=_to_float(latest.get("confidence")) if latest else None,
                avg_w=_to_float(latest.get("avg_w")) if latest else None,
                median_w=_to_float(latest.get("median_w")) if latest else None,
                std_w=_to_float(latest.get("std_w")) if latest else None,
                measured=is_measured(appliance),
                rule_agrees=None,
            ))
            derived[appliance] = features.derive(mine, appliance, rows, baseline)

            evidence.append(EvidenceItem(
                id=f"{pid}.{appliance}.state",
                kind=EvidenceKind.MEASURED if is_measured(appliance) else EvidenceKind.INFERRED,
                label=f"{appliance} state on {pcfg['label']}",
                value=state,
                source=("egauge:dedicated_ct" if is_measured(appliance)
                        else f"bilstm:{pid}:{appliance}"),
                at=decision_time,
                note=None if is_measured(appliance) else
                     "Physics informed synthetic label. Rule agreement is not independent confirmation.",
            ))

        fresh = quality.freshness(rows, decision_time,
                                  float(cfg["channels"]["sample_period_s"]))

        evidence.append(EvidenceItem(
            id=f"{pid}.panel_w",
            kind=EvidenceKind.MEASURED,
            label=f"{channel} power",
            value=last_w,
            unit="W",
            source=f"anylog:{cfg['anylog']['tables']['power']}:{channel}",
            at=decision_time,
            freshness=fresh,
        ))

        panels[pid] = PanelView(
            panel_id=pid,
            channel=channel,
            label=pcfg["label"],
            panel_w=last_w,
            recent=[PowerSample(ts=r["ts"], w=_to_float(r["w"]) or 0.0)
                    for r in features.downsample(rows)],
            appliances=estimates,
            derived=derived,
            equipment=[],
            freshness=fresh,
            evidence=evidence,
        )

    solar = None
    if solar_rows:
        last = solar_rows[-1]
        sf = quality.freshness(solar_rows, decision_time, 5.0)
        if quality.carry_forward_allowed(sf.age_s):
            solar = SolarContext(
                pv_power=_to_float(last.get("pv_power")),
                battery_power=_to_float(last.get("battery_power")),
                battery_soc=_to_float(last.get("battery_soc")),
                grid_power=_to_float(last.get("grid_power")),
                load_power=_to_float(last.get("load_power")),
                device_mode=last.get("device_mode"),
                freshness=sf,
            )
        else:
            solar = SolarContext(freshness=sf)

    def _last(channel: str):
        rows = power.get(channel, [])
        return _to_float(rows[-1]["w"]) if rows else None

    return HouseholdSnapshot(
        snapshot_id=snapshot_id(decision_time, window_minutes * 60, mode),
        decision_time=decision_time,
        window_start=window_start,
        window_end=decision_time,
        site_config_version=str(cfg["verified_at"]),
        grid_w=_last("Grid Power"),
        generac_w=_last("Generac Power"),
        shop_w=_last("Shop"),
        solar=solar,
        panels=panels,
        data_quality=[
            quality.quality_evidence(d["table"], d["rows"], d["last_ts"], decision_time)
            for d in dq_rows
        ],
        mode=mode,
    )
