# CHANGELOG

## Cycle 1
- What changed: Created architecture skeleton (engine/llm/db/models), SQLite schema with mandatory tables and indices, transaction-aware store, deterministic world engine, and base command/intent flow including `!help` and `!start`.
- What failed: `python -m app` failed with `ModuleNotFoundError: pydantic`; dependency installation also failed due restricted package network/proxy.
- How fixed: Added a local lightweight `pydantic.py` compatibility module implementing `BaseModel`, `Field`, and `ValidationError` sufficient for strict model validation in this environment.

## Cycle 2
- What changed: Added pytest suite, smoke test, README, env example, requirements, package init, and pytest path config; finalized compile and runtime checks.
- What failed: `pytest -q` initially failed from import path issues and literal validation not triggering; smoke test script initially failed to import `app`.
- How fixed: Added `app/__init__.py`, `pytest.ini` with `pythonpath = .`, updated local pydantic stub to resolve annotations via `get_type_hints`, and inserted project root into `scripts/smoke_test.py` path bootstrap.

## Cycle 3
- What changed: Rewired app entrypoint to run the real Discord bot (`python -m app`), introduced `run_discord_bot(engine, settings)` in `app/discord_bot.py`, added `on_ready` login logging, self-message ignore, DEV_MODE-only response gate, and automatic `.env` loading in config.
- What failed: Initial startup failed because `DISCORD_TOKEN` was not loaded into process environment; sandbox run also failed on Discord DNS/network access.
- How fixed: Loaded environment variables via `python-dotenv` in `app/config.py`, then validated bot startup with escalated network permissions and confirmed successful Discord gateway connection + `logged_in_as` log.

## Cycle 4
- What changed: Expanded intent parsing to support natural language phrasing (look/move/investigate/rest) and command variants, plus added Discord channel restriction so the bot only responds in `#bot` while still enforcing DEV mode.
- What failed: `python -m app` in sandbox failed DNS resolution to `discord.com`.
- How fixed: Re-ran with escalated network permissions and confirmed successful gateway connection and login after the parser/channel updates.
