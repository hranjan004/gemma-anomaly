# gemma-anomaly

Anomaly detection for a residential microgrid. Three logical panel agents over
one fine-tuned [Gemma](https://ai.google.dev/gemma) adapter, coordinated into a
single reviewable incident.

This layer sits on top of an existing energy pipeline and does not retrain,
replace, or modify it. It reads the same [AnyLog](https://github.com/AnyLog-co/EdgeLake)
deployment the pipeline already writes to, consumes the appliance estimates the
existing NILM models already produce, and adds anomaly assessment above them.

## Why this shape

A household energy pipeline produces two kinds of signal that are easy to
confuse. A handful of circuits carry a dedicated measurement channel, so their
state is known. Everything else is an estimate from a disaggregation model,
often trained on labels a rules layer generated, which means model-and-rule
agreement is not independent confirmation of anything.

An anomaly layer that blurs those two is worse than no anomaly layer, because
it produces confident alerts about appliances nobody can verify. So the central
design commitment here is that measured and inferred evidence never merge.
Every item in a snapshot carries its kind, the prompt says which outranks
which, and an incident reports the two evidence sets separately.

The second commitment is that abstention is a real answer. A stale window with
a missing solar reading should produce `insufficient_evidence` and one targeted
follow-up, not a guess.

The third is that failure has to be visible. A serving endpoint that is down
must not look like a quiet house.

## Layout

```
config/site.example.yaml     copy to config/site.yaml and fill in
config/categories.yaml       anomaly categories, thresholds provisional
docs/ARCHITECTURE.md         data flow, module responsibilities, commitments
docs/ANYLOG_NOTES.md         query behaviors that cost real debugging time
docs/FIELD_NOTES.md          lessons from a live deployment bring-up
docs/VENDOR_SETUP.md         what each vendor requires, with links
docs/BUILD_ORDER.md          schedule and acceptance criteria
src/gemma_anomaly/
  contracts/                 the only place a shape is defined
  evidence/                  bounded AnyLog and Home Assistant readers
  snapshot/                  one immutable snapshot per assessment tick
  agents/                    prompt, call, strict parse
  coordinator/               grouping, dedup, incident identity
  serving/                   base and tuned routes, tracing
  training/                  labels, dataset splits, QLoRA config
  review/                    human review round trip
  replay/                    freeze and replay snapshots
  eval/                      incident matching and metrics
  api/                       FastAPI surface
scripts/verify_site.py       check every config assumption against live data
scripts/smoke_assess.py      build one snapshot, print the agent payload
scripts/export_replay.py     freeze a replay set as a demo backup
scripts/check_adapter.py     prove the adapter is applied, not silently ignored
```

## Setup

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp config/site.example.yaml config/site.yaml
```

Then edit `config/site.yaml` for your deployment and run `make verify`. It
re-checks every channel, panel mapping, and table against the live system and
fails loudly on any mismatch.

`config/site.yaml`, `.env`, and `replay_data/` are gitignored. Panel and
appliance mappings describe a specific building's loads and host addresses
describe a specific private network, so neither belongs in a repository. The
code falls back to `config/site.example.yaml` when no local config exists, which
is how the test suite runs anywhere.

## Use

```
make verify     re-verify site config against the live deployment
make smoke      build one live snapshot and print what an agent sees
make replay     freeze a replay set for offline demos
make adapter    check the tuned route actually differs from the base route
make api        serve /health, /snapshot, /assess, /replay on port 8100
make test       run the contract and coordinator tests
```

`make smoke` and `make verify` need no GPU and no serving endpoint. `make test`
needs neither, and no live deployment either.

Read [docs/VENDOR_SETUP.md](docs/VENDOR_SETUP.md) before standing up the model.
It documents a
[vLLM issue](https://github.com/vllm-project/vllm/issues/41754) where a Gemma 4
LoRA adapter loads without error and is then silently ignored at inference,
which would make the tuned and base routes identical while appearing to work.
`make adapter` exists to catch exactly that.

## Stack

| Component | Role |
|---|---|
| [AnyLog / EdgeLake](https://github.com/AnyLog-co/EdgeLake) | distributed storage for measurements and inference output |
| [Gemma](https://ai.google.dev/gemma) | anomaly assessment, one adapter conditioned on panel identity |
| [PEFT](https://github.com/huggingface/peft) + [TRL](https://github.com/huggingface/trl) | QLoRA supervised fine-tuning |
| [vLLM](https://docs.vllm.ai/) | adapter serving, base and tuned routes |
| [Lambda](https://lambda.ai/) | GPU for training and serving |
| [Respan](https://respan.ai) | gateway tracing and evaluation |
| [Nango](https://docs.nango.dev) | human review round trip via Google Sheets |
| [Home Assistant](https://developers.home-assistant.io/docs/api/rest/) | optional corroborating equipment context |
| [FastAPI](https://fastapi.tiangolo.com/) + [Pydantic](https://docs.pydantic.dev/) | contracts and service surface |

## State

Working and exercised against a live deployment: the evidence layer, the
snapshot builder, contracts, prompt assembly, the strict output parser,
coordinator grouping and deduplication, replay export and load, and evaluation
metrics.

Not built, each raising `NotImplementedError` with the reason rather than
returning a plausible empty result: the SFT trainer, which needs a pinned
checkpoint and a GPU smoke run; the review integration calls, which need a
connection created first; the rules-only baseline detector; and the dashboard.

## License

MIT. See [LICENSE](LICENSE).
