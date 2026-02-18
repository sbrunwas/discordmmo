# DiscordMMO Engine v1

Persistent, deterministic Discord-based MMO campaign engine with an engine-first architecture.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run local entrypoint

```bash
python -m app
```

## Run Discord bot

```bash
python -c "from app.main import build_engine; from app.config import Settings, configure_logging; from app.discord_bot import run_bot; s=Settings(); configure_logging(s.dev_mode); run_bot(s.discord_token, build_engine(s))"
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
