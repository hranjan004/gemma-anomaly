# Architecture

Three logical panel agents over one shared Gemma anomaly adapter, coordinated
into one reviewable incident. The existing eGauge ingestion, AnyLog storage,
BiLSTM/ONNX appliance inference, physical rules layer, and dashboard are kept
unchanged. Only anomaly detection is fine-tuned.

## Data flow

```
eGauge 18646 ──▶ Kafka ──▶ AnyLog operator (32149) ──▶ PostgreSQL
Solar Assistant ──▶ MQTT ──▶ AnyLog (solar_data)
                                    │
                    BiLSTM/ONNX  ───┤  writes nilm_disaggregated every 30 s
                    + rules layer   │
                                    ▼
                        evidence/  bounded query functions
                          get_panel_window
                          get_appliance_estimates
                          get_solar_snapshot
                          get_data_quality
                          ha.get_equipment_context   (optional, LAN only)
                                    │
                                    ▼
                        snapshot/  one immutable HouseholdSnapshot
                                   + three PanelViews
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
        panel1 agent          panel2 agent          panel3 agent
        (HVAC)                (H2O)                 (Kitchen)
              └─────────────────────┼─────────────────────┘
                                    ▼
                        coordinator/  group, dedup, one Incident
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              dashboard        Respan traces    Nango → Google Sheet
                                                       │
                                                 ReviewOutcome
                                                       ▼
                                            training/ dataset release
```

Serving sits between the agents and Gemma. Every call carries a snapshot id,
panel id, model and adapter version, and prompt version, so an alert traces
back to its exact input.

## Module responsibilities

`contracts/` is the only place a shape is defined. `snapshot.py` holds the
evidence contracts, `findings.py` the agent and coordinator outputs,
`review.py` the human review round trip. Everything downstream imports these
rather than passing dictionaries around.

`evidence/` reads AnyLog and Home Assistant through a fixed set of bounded
functions. There is no free-form command surface, because agents never touch the
database. `anylog.py` carries the transport quirks documented in
[`ANYLOG_NOTES.md`](ANYLOG_NOTES.md). `features.py` computes duration, switching counts,
energy, duty cycle, and baseline deviation in ordinary code, so the model is
given numbers to judge rather than arithmetic to perform. `quality.py` produces
freshness, gap, and frozen-value flags.

`snapshot/builder.py` assembles one immutable snapshot per tick. Nothing
measured after `decision_time` enters it, a carried-forward value is dropped
past `max_carry_forward_s`, and a later solar reading is never joined into an
earlier power window. The same object serves live, replay, and synthetic modes,
which is what makes a saved snapshot reproduce a request exactly.

`agents/` is one agent class, run three times with a different panel id.
`prompts.py` is versioned and builds the household plus panel payload.
`parser.py` validates the answer strictly: unknown category, an appliance not
mapped to that panel, an unresolvable evidence id, or a volunteered confidence
number all produce `INVALID_OUTPUT`. A failed call never becomes "normal" and
never silently falls back to another model.

`coordinator/` groups findings by time and equipment, keeps links to all
originals, bounds follow-ups to one per affected panel, and assigns a stable
`incident_id` from a fingerprint plus a time bucket, so a retry updates the same
review row instead of creating a duplicate. If grouping raises, the incident is
still produced from the original findings with `coordination_error` set. Alerts
are never lost to a coordinator failure.

`serving/` exposes a base route and a tuned route against the same endpoint so
the untuned and tuned models can be compared on identical inputs.
`respan.py` builds the trace headers.

`training/` holds label provenance, dataset assembly with chronological splits
that never split an incident and never leak lookback context across a boundary,
and the QLoRA configuration. `sft.build_trainer` is deliberately unimplemented
until the checkpoint revision is pinned and a smoke run has measured memory and
throughput on the allocated GPU.

`review/nango_sheet.py` maps an incident to a sheet row and validates an
imported review. Appliance confirmation and anomaly confirmation are separate
fields, because a confirmed pump run is not an abnormal pump run.

`eval/metrics.py` fixes incident matching and deduplication before any results
are inspected, counts all monitored time in the false-alert denominator, and
reports by label provenance so verified, weak, and synthetic never blur.

`replay/` freezes a range of snapshots to disk and replays them through the same
agents and coordinator. This is the demo backup for when the link to the
deployment host drops.

## Design commitments

Three logical agents, one model. Panel identity is a prompt condition, not a
separate deployment. Three separately trained adapters stay an optional
experiment and are the first thing cut if time runs short.

Measured and inferred evidence never merge. Only the heads listed under
`evidence_quality.measured` in `config/site.yaml` have a dedicated CT. Every
other appliance state is an estimate resting on physics-informed synthetic
labels, and the snapshot says so on every item. On a typical deployment this is
a small minority of heads.

Abstention is a real answer. `insufficient_evidence` with one targeted follow-up
beats a confident guess on a stale window.

Solar context is required before any grid-balance claim. A fall in PV raises
grid import with no appliance anomaly behind it, and a normal household total
can hide unusual activity inside one panel.

No numeric confidence from the model. Head scores are model estimates, not
calibrated probabilities, and the parser rejects an answer that asserts one.

## What is not built yet

`training/sft.build_trainer` and `smoke_run`, both of which belong on the GPU
instance. `review/nango_sheet.export_incident` and `import_reviews`, which need
the Nango connection created first. The rules-only baseline detector, which is
the third arm of the comparison and the source of the initial weak labels. The
dashboard views. Each raises `NotImplementedError` with the reason rather than
returning a plausible empty result.
