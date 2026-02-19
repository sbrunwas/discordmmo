# DiscordMMO Engine v1

Persistent, deterministic Discord-based MMO campaign engine with an engine-first architecture.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Never commit real API keys. This is a public repo. Keep secrets only in local environment variables or a local `.env` file.

## Run Discord bot

```bash
python -m app
```

## Tests

```bash
pytest -q
python -m compileall app
python scripts/smoke_test.py
```

## Commands

- `!help`
- `!start`
- `!stats`
- `!inventory`
- `!skills`
- `!respec`
- `!factions`
- `!recap`
- `!recap arc`
- `!recap faction`
- `!recap location`
- `!rest short`
- `!rest long`
- `!duel @user`
- `talk to <npc>`
- `speak with <npc>`

## LLM configuration (OpenRouter)

Set these in your shell or local `.env`:

- `LLM_BACKEND=stub|openrouter` (default: `stub`)
- `OPENROUTER_API_KEY=...` (required when `LLM_BACKEND=openrouter`)
- `OPENROUTER_MODEL=openrouter/free` (default)
- `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1`
- `LLM_MAX_CALLS_PER_DAY=50`
- `LLM_MAX_CALLS_PER_USER_PER_DAY=10`
- `LLM_MAX_INPUT_CHARS=600`

Safety behavior:

- If OpenRouter is disabled, misconfigured, rate-limited, or errors, the app falls back to stub behavior.
- Input sent to LLM is truncated to `LLM_MAX_INPUT_CHARS`.
- Daily global and per-user limits are enforced.

NPC dialogue:

- NPCs have seeded personalities and location-specific behavior prompts.
- Dialogue uses per-player conversation memory so follow-up messages stay contextual.

Git hygiene:

- `.gitignore` includes `.env`, `*.db`, and `venv/` to prevent leaking keys/local state.
