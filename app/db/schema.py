from __future__ import annotations

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS players (
    player_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    location_id TEXT NOT NULL,
    hp INTEGER NOT NULL,
    xp INTEGER NOT NULL DEFAULT 0,
    injury INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS npcs (
    npc_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    location_id TEXT NOT NULL,
    is_key INTEGER NOT NULL DEFAULT 0,
    alive INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS factions (
    faction_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sentiment INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS locations (
    location_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    is_permanent INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    location_id TEXT,
    data_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS arc_state (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS encounters (
    encounter_id TEXT PRIMARY KEY,
    location_id TEXT NOT NULL,
    state_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    ts DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS proposals (
    proposal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id TEXT NOT NULL,
    proposal_type TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    ts DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS npc_profiles (
    npc_id TEXT PRIMARY KEY,
    persona_prompt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS npc_dialogue_memory (
    memory_id INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    ts DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS llm_usage (
    day TEXT NOT NULL,
    user_id TEXT NOT NULL,
    calls INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(day, user_id)
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_actor_id ON events(actor_id);
CREATE INDEX IF NOT EXISTS idx_encounters_location_id ON encounters(location_id);
CREATE INDEX IF NOT EXISTS idx_llm_usage_day ON llm_usage(day);
CREATE INDEX IF NOT EXISTS idx_npc_memory_lookup ON npc_dialogue_memory(npc_id, player_id, memory_id);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
