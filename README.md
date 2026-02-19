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

# Hybrid LLM defaults: OpenRouter for JSON intent parsing, Ollama for narration/NPC text
LLM_JSON_BACKEND=openrouter
LLM_TEXT_BACKEND=ollama
OPENROUTER_API_KEY=your_openrouter_key_here
OPENROUTER_MODEL=openrouter/auto:free
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b-instruct
OLLAMA_AUTOSTART=1

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

If OpenRouter fails or keys are missing, JSON parsing falls back safely. If Ollama is unavailable, narration/NPC text falls back to stub safely.

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

## LLM configuration (Hybrid)

Set these in your shell or local `.env`:

- `LLM_JSON_BACKEND=stub|openrouter` (default: `openrouter`)
- `LLM_TEXT_BACKEND=stub|openrouter|ollama` (default: `ollama`)
- `OPENROUTER_API_KEY=...` (required when using OpenRouter)
- `OPENROUTER_MODEL=openrouter/auto:free` (default)
- `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1`
- `OLLAMA_BASE_URL=http://127.0.0.1:11434`
- `OLLAMA_MODEL=qwen2.5:7b-instruct`
- `OLLAMA_AUTOSTART=1`
- `OLLAMA_START_TIMEOUT_SECONDS=20`
- `LLM_MAX_CALLS_PER_DAY=50`
- `LLM_MAX_CALLS_PER_USER_PER_DAY=10`
- `LLM_MAX_INPUT_CHARS=600`

Safety behavior:

- `python -m app` auto-starts Ollama when text backend is `ollama` and autostart is enabled.
- If Ollama is unavailable or autostart fails, text generation falls back to stub without crashing startup.
- If OpenRouter is disabled, misconfigured, rate-limited, or errors, intent parsing falls back to stub behavior.
- Input sent to LLM is truncated to `LLM_MAX_INPUT_CHARS`.
- Daily global and per-user limits are enforced for OpenRouter calls.

NPC dialogue:

- NPCs have seeded personalities and location-specific behavior prompts.
- Dialogue uses per-player conversation memory so follow-up messages stay contextual.

NPC realism (`npcforge`):

- NPCs use persistent character sheets (alignment, background, ideals/bonds/flaws, motivation/fear, archetype, skills, voice).
- Dynamic NPC state tracks mood, current goal, memory summary, pinned memories, and per-player relationship metrics (affinity/trust/respect/bonds/grudges).
- TALK interactions run through a structured Observation -> NPCOutput contract, then engine compiles safe candidate actions or logs flavor-only outcomes.
- Autonomous planner ticks can move NPCs or trigger social flavor actions with strict guardrails (no arc advancement, no off-screen key-NPC deaths).

Continuity features:

- Structured per-player scene memory (`mode`, `location`, `last_action`, `active_thread_id`).
- Thread tracking for travel, combat, mystery beats, and NPC conversations.
- Confidence gate for low-confidence `UNKNOWN` intents with clarifying responses.
- Anti-loop guard that adds progression nudges on repeated bot output.
- Per-NPC/player dialogue summaries to keep long conversations coherent.

Git hygiene:

- `.gitignore` includes `.env`, `*.db`, and `venv/` to prevent leaking keys/local state.
