# DiscordMMO Engine v1

Persistent, deterministic Discord-based MMO campaign engine with an engine-first architecture.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

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
