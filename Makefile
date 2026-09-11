PY := python3
SRC := PYTHONPATH=src

.PHONY: verify smoke replay api test adapter

verify:
	$(PY) scripts/verify_site.py

smoke:
	$(PY) scripts/smoke_assess.py

replay:
	$(PY) scripts/export_replay.py --hours 6 --step-minutes 10 --name demo

api:
	$(SRC) uvicorn gemma_anomaly.api.app:app --host 0.0.0.0 --port 8100

test:
	$(SRC) $(PY) -m pytest tests -q

adapter:
	$(PY) scripts/check_adapter.py
