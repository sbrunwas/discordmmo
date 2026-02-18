# CHANGELOG

## Cycle 1
- What changed: Created architecture skeleton (engine/llm/db/models), SQLite schema with mandatory tables and indices, transaction-aware store, deterministic world engine, and base command/intent flow including `!help` and `!start`.
- What failed: `python -m app` failed with `ModuleNotFoundError: pydantic`; dependency installation also failed due restricted package network/proxy.
- How fixed: Added a local lightweight `pydantic.py` compatibility module implementing `BaseModel`, `Field`, and `ValidationError` sufficient for strict model validation in this environment.

## Cycle 2
- What changed: Added pytest suite, smoke test, README, env example, requirements, package init, and pytest path config; finalized compile and runtime checks.
- What failed: `pytest -q` initially failed from import path issues and literal validation not triggering; smoke test script initially failed to import `app`.
- How fixed: Added `app/__init__.py`, `pytest.ini` with `pythonpath = .`, updated local pydantic stub to resolve annotations via `get_type_hints`, and inserted project root into `scripts/smoke_test.py` path bootstrap.
