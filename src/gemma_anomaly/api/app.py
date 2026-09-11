"""FastAPI surface.

Bounded endpoints only. There is no free form database or model command here.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..contracts.findings import Incident
from ..contracts.snapshot import HouseholdSnapshot
from ..coordinator import workflow
from ..evidence import anylog
from ..replay import runner
from ..serving import client
from ..settings import site
from ..snapshot.builder import build

app = FastAPI(title="Gemma Anomaly", version="0.1.0")


class AssessRequest(BaseModel):
    decision_time: datetime | None = None
    window_minutes: int = 30
    route: str = "base"          # base | tuned
    mode: str = "live"


@app.get("/health")
def health() -> dict:
    return {
        "anylog": anylog.health(),
        "serving": client.health(),
        "site_config_version": site()["verified_at"],
    }


@app.post("/snapshot", response_model=HouseholdSnapshot)
def snapshot(req: AssessRequest) -> HouseholdSnapshot:
    return build(req.decision_time, req.window_minutes, req.mode)


@app.post("/assess", response_model=list[Incident])
def assess(req: AssessRequest) -> list[Incident]:
    route = client.tuned_route() if req.route == "tuned" else client.base_route()
    snap = build(req.decision_time, req.window_minutes, req.mode)
    return workflow.assess(snap, route)


@app.post("/replay/{name}", response_model=list[Incident])
def replay(name: str, route: str = "base") -> list[Incident]:
    from ..replay.export import REPLAY_DIR

    directory = REPLAY_DIR / name
    if not (directory / "manifest.json").exists():
        raise HTTPException(404, f"no replay set named {name}")
    chosen = client.tuned_route() if route == "tuned" else client.base_route()
    return runner.replay_set(directory, chosen)
