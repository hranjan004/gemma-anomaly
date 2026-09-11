#!/usr/bin/env python3
"""Prove the adapter is actually applied before trusting any comparison.

vLLM issue 41754: a Gemma 4 LoRA adapter can load without an error and then be
ignored during inference. It is silent. A silently ignored adapter makes the
tuned route and the base route produce identical answers, which would be
reported as a fine-tuned deployment that never ran.

This sends the same snapshots to both routes and fails if the outputs match.
Run it before the evaluation, not after.
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gemma_anomaly.agents import panel_agent                      # noqa: E402
from gemma_anomaly.contracts.findings import CallStatus           # noqa: E402
from gemma_anomaly.replay.runner import load_snapshot             # noqa: E402
from gemma_anomaly.serving.client import base_route, tuned_route  # noqa: E402
from gemma_anomaly.snapshot.builder import PANEL_IDS              # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshots", default="replay_data/*.json")
    ap.add_argument("--limit", type=int, default=3)
    args = ap.parse_args()

    paths = sorted(glob.glob(args.snapshots))[: args.limit]
    if not paths:
        print(f"no snapshots matched {args.snapshots}. Run scripts/export_replay.py first.")
        return 2

    base, tuned = base_route(), tuned_route()
    if not tuned.adapter:
        print("GEMMA_ADAPTER is unset. Nothing to check.")
        return 2

    identical, compared, failures = 0, 0, 0

    for path in paths:
        snap = load_snapshot(path)
        for panel_id in PANEL_IDS:
            a = panel_agent.assess(snap, panel_id, base)
            b = panel_agent.assess(snap, panel_id, tuned)

            if a.status is not CallStatus.OK and a.status.value != "invalid_output":
                print(f"  {snap.snapshot_id} {panel_id} base call failed: {a.error}")
                failures += 1
                continue
            if b.status is not CallStatus.OK and b.status.value != "invalid_output":
                print(f"  {snap.snapshot_id} {panel_id} tuned call failed: {b.error}")
                failures += 1
                continue

            compared += 1
            same = (a.raw_output or "").strip() == (b.raw_output or "").strip()
            identical += same
            print(f"  {snap.snapshot_id} {panel_id} "
                  f"{'IDENTICAL' if same else 'differs'}")

    if failures:
        print(f"\n{failures} calls failed. Fix the endpoint before reading this result.")
        return 2
    if not compared:
        print("\nNothing compared.")
        return 2

    print(f"\n{identical} of {compared} comparisons identical.")
    if identical == compared:
        print(
            "FAIL: every answer matched. The adapter is almost certainly not "
            "applied (vLLM issue 41754). Merge the adapter into the base weights "
            "and serve the merged model, serve through Unsloth FastModel, or fall "
            "back to Gemma 3. Do not report a fine-tuned result from this setup."
        )
        return 1

    print("PASS: the adapter changes the output, so it is being applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
