#!/usr/bin/env python3
"""Build one live snapshot and print what an agent would receive.

Runs without a GPU or a serving endpoint. Use it to check the evidence layer and
the prompt payload before any model exists.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gemma_anomaly.agents import prompts           # noqa: E402
from gemma_anomaly.snapshot.builder import build   # noqa: E402


def main() -> int:
    snap = build(window_minutes=30)
    print(f"snapshot {snap.snapshot_id} at {snap.decision_time} mode={snap.mode}")
    print(f"grid={snap.grid_w} generac={snap.generac_w} shop={snap.shop_w}")
    if snap.solar:
        print(f"solar pv={snap.solar.pv_power} soc={snap.solar.battery_soc} "
              f"stale={snap.solar.freshness.stale if snap.solar.freshness else '?'}")

    for pid, view in snap.panels.items():
        on = [a.appliance for a in view.appliances if a.state == "on"]
        print(f"\n{pid} {view.channel} w={view.panel_w} "
              f"stale={view.freshness.stale if view.freshness else '?'} on={on or 'none'}")
        for appliance, d in view.derived.items():
            if d.run_duration_s:
                print(f"    {appliance}: run {d.run_duration_s:.0f}s "
                      f"switches/h {d.switches_per_h:.1f} duty {d.duty_cycle:.2f}")

    messages = prompts.build_messages(snap, "panel3")
    payload = json.loads(messages[1]["content"])
    print(f"\npanel3 prompt payload: {len(messages[1]['content'])} chars, "
          f"{len(payload['panel']['evidence'])} evidence ids")

    out = Path(__file__).resolve().parents[1] / "replay_data" / f"{snap.snapshot_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(snap.model_dump_json(indent=2))
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
