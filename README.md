# DiscordMMO Engine v1

Persistent, deterministic Discord-based MMO campaign engine with an engine-first architecture.

## Run locally (quick start)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

1. Edit `.env` and set your keys:

```env
# Required to run the Discord bot
DISCORD_TOKEN=your_discord_bot_token_here

# Use OpenRouter for LLM responses
LLM_BACKEND=openrouter
OPENROUTER_API_KEY=your_openrouter_key_here
OPENROUTER_MODEL=arcee-ai/trinity-large-preview:free
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Optional local defaults
DEV_MODE=1
DB_PATH=world_dev.db
```

2. In the Discord Developer Portal, ensure your bot has:
- `MESSAGE CONTENT INTENT` enabled (required)
- proper permissions/invite to your server and channel

3. Start the bot:

```bash
python -m app
```

4. Chat with bot in Discord in # bot channel.

Never commit real API keys. This is a public repo. Keep secrets only in local environment variables or a local `.env` file.

If OpenRouter fails or keys are missing, the app falls back to stub mode automatically.

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

Continuity features:

- Structured per-player scene memory (`mode`, `location`, `last_action`, `active_thread_id`).
- Thread tracking for travel, combat, mystery beats, and NPC conversations.
- Confidence gate for low-confidence `UNKNOWN` intents with clarifying responses.
- Anti-loop guard that adds progression nudges on repeated bot output.
- Per-NPC/player dialogue summaries to keep long conversations coherent.

Git hygiene:

- `.gitignore` includes `.env`, `*.db`, and `venv/` to prevent leaking keys/local state.
