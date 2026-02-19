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

## Cycle 5
- What changed: Migrated LLM backend to OpenRouter-compatible chat completions with env-based config (`LLM_BACKEND`, `OPENROUTER_*`), added strict input truncation and daily usage guardrails (global + per-user) backed by persisted SQLite `llm_usage`, and updated intent parsing to attempt LLM on `UNKNOWN` while preserving deterministic engine behavior with safe fallbacks.
- What failed: Tests initially broke due `LLMClient` constructor/API changes and missing coverage for fallback/limits behavior.
- How fixed: Updated wiring in `app/main.py`, parser callers, smoke/test setup, added `tests/test_llm_client.py` for stub/no-key/rate-limit scenarios, and documented secure env setup in `README.md`/`.env.example`.

## Cycle 6
- What changed: Added NPC conversation system with `TALK` intent, seeded NPC personalities, LLM-driven in-character dialogue generation, and persisted per-player NPC memory via new SQLite tables (`npc_profiles`, `npc_dialogue_memory`).
- What failed: Social interaction text previously collapsed into generic investigation/look loops with no conversational continuity.
- How fixed: Routed social language to `TALK`, added location NPC discovery + target resolution, injected persona/history context into `app/llm/npc_dialogue.py`, and added regression tests for memory persistence and talk flow.

## Cycle 7
- What changed: Implemented continuity control layer with persistent session state (`mode`, active NPC/encounter/thread), structured scene memory, player thread tracking, confidence-gated clarifications, anti-loop response nudges, and per-NPC dialogue summaries.
- What failed: Narrative flow could reset between turns, and ambiguous follow-ups could derail into unrelated scene/combat states.
- How fixed: Added continuity tables + store APIs, wired world engine turn resolution through `_respond(...)` observability/logging path, injected scene/session context into intent parsing, and added continuity regression tests (`tests/test_continuity.py`).

## Cycle 8
- What changed: Removed DEV-only runtime gate from Discord message handling, moved engine execution off the event loop via `asyncio.to_thread`, switched RNG to always use configured seed, hardened SQLite for threaded access (`check_same_thread=False` + lock), added one-time world seeding guard, expanded command handling for documented commands, improved location-based movement resolution, and made exploration prompts dynamic from current NPC/location data.
- What failed: Command coverage and movement were previously too rigid (`town_square` fallback), and production deployment silently no-op'd when `DEV_MODE` was false.
- How fixed: Added explicit command intents and handlers (`STATS/INVENTORY/SKILLS/RESPEC/FACTIONS/RECAP/DUEL`), implemented `_resolve_move_target(...)`, introduced seed version check via `WORLD_SEED_VERSION`, and integrated rules-based rolls into combat with XP/injury effects.

## Cycle 9
- What changed: Implemented Hybrid LLM (OpenRouter JSON + Ollama text) + Ollama autostart, including split backend config (`LLM_JSON_BACKEND`, `LLM_TEXT_BACKEND`), provider-based LLM client routing, OpenRouter JSON validation with strict fallback, Ollama runtime healthcheck/autostart, and startup-time fallback to stub text generation when Ollama is unavailable.
- What failed: Existing tests assumed a single `LLM_BACKEND` flow and would route text paths into unavailable local Ollama defaults.
- How fixed: Updated tests/config docs for split backends, added hybrid routing/autostart fallback coverage, and preserved compatibility via safe stub fallbacks without crashing `python -m app`.

## Cycle 10
- What changed: Added in-repo `app/npcforge` package (schemas, generator, policy, memory, planner, compiler, templates) and integrated it into NPC TALK flow with persistent NPC sheet/state in `npcs.persona_json` + `npcs.memory_json`; added planner tick execution path with guardrails and `npc_tick` tagging, plus relationship/memory event logging (`NPC_SPOKE`, `NPC_STATE_UPDATED`, `FLAVOR_ONLY`, `NPC_TICK`).
- What failed: Existing schema/store methods did not support structured NPC persona/state persistence, and there was no safe compiler path from open-ended NPC candidate actions to deterministic world changes.
- How fixed: Extended DB schema with backward-compatible migrations (`persona_json`, `memory_json`, `npc_last_tick_ts`), added Store helpers for NPC forge state, implemented bounded memory/relationship updates and safe action compilation, and added tests + smoke coverage for relationship shifts and planner tick outcomes.
