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
    actor_id TEXT,
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
CREATE TABLE IF NOT EXISTS npc_dialogue_summaries (
    npc_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    updated_ts DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(npc_id, player_id)
);
CREATE TABLE IF NOT EXISTS player_session_state (
    player_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL DEFAULT 'explore',
    active_npc_id TEXT,
    active_encounter_id TEXT,
    active_thread_id TEXT,
    last_bot_message TEXT,
    repeat_count INTEGER NOT NULL DEFAULT 0,
    updated_ts DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS player_scene_memory (
    player_id TEXT PRIMARY KEY,
    scene_json TEXT NOT NULL,
    updated_ts DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS player_threads (
    player_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    thread_type TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    last_message TEXT NOT NULL DEFAULT '',
    updated_ts DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(player_id, thread_id)
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
CREATE INDEX IF NOT EXISTS idx_player_threads_status ON player_threads(player_id, status);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(encounters)").fetchall()}
    if "actor_id" not in columns:
        conn.execute("ALTER TABLE encounters ADD COLUMN actor_id TEXT DEFAULT 'global'")
    conn.commit()
