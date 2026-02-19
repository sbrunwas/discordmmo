from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.db.schema import init_db

log = logging.getLogger(__name__)


class Store:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        init_db(self.conn)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            log.info("transaction_start")
            try:
                yield self.conn
                self.conn.commit()
                log.info("transaction_commit")
            except Exception:
                self.conn.rollback()
                log.exception("transaction_rollback")
                raise

    def write_event(self, actor_id: str, event_type: str, payload: dict[str, Any]) -> None:
        log.info("event_write actor=%s type=%s", actor_id, event_type)
        with self.tx() as conn:
            conn.execute(
                "INSERT INTO events(actor_id, event_type, payload_json) VALUES (?, ?, ?)",
                (actor_id, event_type, json.dumps(payload, sort_keys=True)),
            )

    def create_player(self, player_id: str, name: str, location_id: str) -> None:
        with self.tx() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO players(player_id, name, location_id, hp, xp, injury) VALUES (?, ?, ?, 20, 0, 0)",
                (player_id, name, location_id),
            )

    def get_player(self, player_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute("SELECT * FROM players WHERE player_id = ?", (player_id,)).fetchone()

    def get_session_state(self, player_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT mode, active_npc_id, active_encounter_id, active_thread_id, last_bot_message, repeat_count
                FROM player_session_state
                WHERE player_id = ?
                """,
                (player_id,),
            ).fetchone()
        if row is None:
            return {
                "mode": "explore",
                "active_npc_id": None,
                "active_encounter_id": None,
                "active_thread_id": None,
                "last_bot_message": "",
                "repeat_count": 0,
            }
        return {
            "mode": row["mode"],
            "active_npc_id": row["active_npc_id"],
            "active_encounter_id": row["active_encounter_id"],
            "active_thread_id": row["active_thread_id"],
            "last_bot_message": row["last_bot_message"] or "",
            "repeat_count": int(row["repeat_count"] or 0),
        }

    def upsert_session_state(
        self,
        player_id: str,
        *,
        mode: str,
        active_npc_id: str | None,
        active_encounter_id: str | None,
        active_thread_id: str | None,
        last_bot_message: str,
        repeat_count: int,
    ) -> None:
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO player_session_state(
                    player_id, mode, active_npc_id, active_encounter_id, active_thread_id, last_bot_message, repeat_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_id) DO UPDATE SET
                    mode = excluded.mode,
                    active_npc_id = excluded.active_npc_id,
                    active_encounter_id = excluded.active_encounter_id,
                    active_thread_id = excluded.active_thread_id,
                    last_bot_message = excluded.last_bot_message,
                    repeat_count = excluded.repeat_count,
                    updated_ts = CURRENT_TIMESTAMP
                """,
                (
                    player_id,
                    mode,
                    active_npc_id,
                    active_encounter_id,
                    active_thread_id,
                    last_bot_message,
                    repeat_count,
                ),
            )

    def get_scene_memory(self, player_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.conn.execute(
                "SELECT scene_json FROM player_scene_memory WHERE player_id = ?",
                (player_id,),
            ).fetchone()
        if row is None:
            return {}
        try:
            data = json.loads(row["scene_json"])
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def upsert_scene_memory(self, player_id: str, scene: dict[str, Any]) -> None:
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO player_scene_memory(player_id, scene_json)
                VALUES (?, ?)
                ON CONFLICT(player_id) DO UPDATE SET
                    scene_json = excluded.scene_json,
                    updated_ts = CURRENT_TIMESTAMP
                """,
                (player_id, json.dumps(scene, sort_keys=True)),
            )

    def has_visited_location(self, player_id: str, location_id: str) -> bool:
        scene = self.get_scene_memory(player_id)
        visited = scene.get("locations_visited", [])
        if not isinstance(visited, list):
            return False
        return location_id in visited

    def mark_location_visited(self, player_id: str, location_id: str) -> None:
        scene = self.get_scene_memory(player_id)
        visited = scene.get("locations_visited", [])
        if not isinstance(visited, list):
            visited = []
        if location_id not in visited:
            visited.append(location_id)
        scene["locations_visited"] = visited
        self.upsert_scene_memory(player_id, scene)

    def move_player(self, player_id: str, location_id: str) -> None:
        with self.tx() as conn:
            conn.execute("UPDATE players SET location_id=? WHERE player_id=?", (location_id, player_id))

    def update_player_progress(self, player_id: str, hp_delta: int = 0, xp_delta: int = 0, injury_delta: int = 0) -> None:
        with self.tx() as conn:
            conn.execute(
                """
                UPDATE players
                SET hp = MAX(0, hp + ?),
                    xp = MAX(0, xp + ?),
                    injury = MAX(0, injury + ?)
                WHERE player_id = ?
                """,
                (hp_delta, xp_delta, injury_delta, player_id),
            )

    def upsert_location(self, location_id: str, name: str, description: str) -> None:
        with self.tx() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO locations(location_id, name, description) VALUES (?, ?, ?)",
                (location_id, name, description),
            )

    def get_location(self, location_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute("SELECT * FROM locations WHERE location_id=?", (location_id,)).fetchone()

    def list_locations(self) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute("SELECT * FROM locations ORDER BY name").fetchall()

    def set_arc_value(self, key: str, value: dict[str, Any]) -> None:
        with self.tx() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO arc_state(key, value_json) VALUES (?, ?)",
                (key, json.dumps(value, sort_keys=True)),
            )

    def upsert_npc(
        self,
        npc_id: str,
        name: str,
        location_id: str,
        is_key: bool = False,
        alive: bool = True,
        persona_json: dict[str, Any] | None = None,
        memory_json: dict[str, Any] | None = None,
        npc_last_tick_ts: int = 0,
    ) -> None:
        persona_payload = json.dumps(persona_json or {}, sort_keys=True)
        memory_payload = json.dumps(memory_json or {}, sort_keys=True)
        with self.tx() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO npcs(npc_id, name, location_id, is_key, alive, persona_json, memory_json, npc_last_tick_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    npc_id,
                    name,
                    location_id,
                    1 if is_key else 0,
                    1 if alive else 0,
                    persona_payload,
                    memory_payload,
                    int(npc_last_tick_ts),
                ),
            )

    def list_npcs_at_location(self, location_id: str) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(
                """
                SELECT npc_id, name, location_id, is_key, alive, persona_json, memory_json, npc_last_tick_ts
                FROM npcs
                WHERE location_id = ? AND alive = 1
                ORDER BY name
                """,
                (location_id,),
            ).fetchall()

    def list_npcs(self) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(
                """
                SELECT npc_id, name, location_id, is_key, alive, persona_json, memory_json, npc_last_tick_ts
                FROM npcs
                WHERE alive = 1
                ORDER BY npc_last_tick_ts ASC, name ASC
                """
            ).fetchall()

    def get_npc(self, npc_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(
                """
                SELECT npc_id, name, location_id, is_key, alive, persona_json, memory_json, npc_last_tick_ts
                FROM npcs
                WHERE npc_id = ?
                """,
                (npc_id,),
            ).fetchone()

    def move_npc(self, npc_id: str, location_id: str) -> None:
        with self.tx() as conn:
            conn.execute("UPDATE npcs SET location_id = ? WHERE npc_id = ?", (location_id, npc_id))

    def update_npc_persona(self, npc_id: str, persona_json: dict[str, Any]) -> None:
        with self.tx() as conn:
            conn.execute(
                "UPDATE npcs SET persona_json = ? WHERE npc_id = ?",
                (json.dumps(persona_json, sort_keys=True), npc_id),
            )

    def update_npc_memory(self, npc_id: str, memory_json: dict[str, Any]) -> None:
        with self.tx() as conn:
            conn.execute(
                "UPDATE npcs SET memory_json = ? WHERE npc_id = ?",
                (json.dumps(memory_json, sort_keys=True), npc_id),
            )

    def update_npc_last_tick_ts(self, npc_id: str, ts: int) -> None:
        with self.tx() as conn:
            conn.execute("UPDATE npcs SET npc_last_tick_ts = ? WHERE npc_id = ?", (int(ts), npc_id))

    def get_npc_persona_json(self, npc_id: str) -> dict[str, Any]:
        row = self.get_npc(npc_id)
        if row is None:
            return {}
        raw = row["persona_json"]
        try:
            data = json.loads(raw) if isinstance(raw, str) else {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get_npc_memory_json(self, npc_id: str) -> dict[str, Any]:
        row = self.get_npc(npc_id)
        if row is None:
            return {}
        raw = row["memory_json"]
        try:
            data = json.loads(raw) if isinstance(raw, str) else {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def upsert_npc_profile(self, npc_id: str, persona_prompt: str) -> None:
        with self.tx() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO npc_profiles(npc_id, persona_prompt) VALUES (?, ?)",
                (npc_id, persona_prompt),
            )

    def get_npc_profile(self, npc_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(
                "SELECT npc_id, persona_prompt FROM npc_profiles WHERE npc_id = ?",
                (npc_id,),
            ).fetchone()

    def append_npc_dialogue(self, npc_id: str, player_id: str, role: str, content: str) -> None:
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO npc_dialogue_memory(npc_id, player_id, role, content)
                VALUES (?, ?, ?, ?)
                """,
                (npc_id, player_id, role, content),
            )

    def get_npc_dialogue_history(self, npc_id: str, player_id: str, limit: int = 10) -> list[dict[str, str]]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT role, content
                FROM npc_dialogue_memory
                WHERE npc_id = ? AND player_id = ?
                ORDER BY memory_id DESC
                LIMIT ?
                """,
                (npc_id, player_id, limit),
            ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    def trim_npc_dialogue_history(self, npc_id: str, player_id: str, keep_last: int = 4) -> None:
        with self.tx() as conn:
            conn.execute(
                """
                DELETE FROM npc_dialogue_memory
                WHERE memory_id IN (
                    SELECT memory_id
                    FROM npc_dialogue_memory
                    WHERE npc_id = ? AND player_id = ?
                    ORDER BY memory_id DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (npc_id, player_id, keep_last),
            )

    def get_npc_dialogue_summary(self, npc_id: str, player_id: str) -> str:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT summary_text
                FROM npc_dialogue_summaries
                WHERE npc_id = ? AND player_id = ?
                """,
                (npc_id, player_id),
            ).fetchone()
        if row is None:
            return ""
        return str(row["summary_text"] or "")

    def upsert_npc_dialogue_summary(self, npc_id: str, player_id: str, summary_text: str) -> None:
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO npc_dialogue_summaries(npc_id, player_id, summary_text)
                VALUES (?, ?, ?)
                ON CONFLICT(npc_id, player_id) DO UPDATE SET
                    summary_text = excluded.summary_text,
                    updated_ts = CURRENT_TIMESTAMP
                """,
                (npc_id, player_id, summary_text),
            )

    def upsert_thread(
        self,
        player_id: str,
        thread_id: str,
        thread_type: str,
        title: str,
        last_message: str,
        status: str = "ACTIVE",
    ) -> None:
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO player_threads(player_id, thread_id, thread_type, title, status, last_message)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_id, thread_id) DO UPDATE SET
                    thread_type = excluded.thread_type,
                    title = excluded.title,
                    status = excluded.status,
                    last_message = excluded.last_message,
                    updated_ts = CURRENT_TIMESTAMP
                """,
                (player_id, thread_id, thread_type, title, status, last_message[:500]),
            )

    def add_proposal(self, actor_id: str, proposal_type: str, content: str) -> None:
        with self.tx() as conn:
            conn.execute(
                "INSERT INTO proposals(actor_id, proposal_type, content) VALUES (?, ?, ?)",
                (actor_id, proposal_type, content),
            )

    def get_recent_events(self, actor_id: str, limit: int = 6) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT event_type, payload_json, ts
                FROM events
                WHERE actor_id = ?
                ORDER BY event_id DESC
                LIMIT ?
                """,
                (actor_id, limit),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in reversed(rows):
            try:
                payload = json.loads(row["payload_json"])
            except Exception:
                payload = {}
            items.append(
                {
                    "event_type": row["event_type"],
                    "payload": payload,
                    "ts": row["ts"],
                }
            )
        return items

    def try_consume_llm_call(
        self,
        day: str,
        user_id: str,
        max_calls_per_day: int,
        max_calls_per_user_per_day: int,
    ) -> tuple[bool, str | None]:
        with self.tx() as conn:
            global_calls = conn.execute(
                "SELECT COALESCE(SUM(calls), 0) AS total FROM llm_usage WHERE day = ?",
                (day,),
            ).fetchone()["total"]
            if global_calls >= max_calls_per_day:
                return False, "global_limit"

            row = conn.execute(
                "SELECT calls FROM llm_usage WHERE day = ? AND user_id = ?",
                (day, user_id),
            ).fetchone()
            user_calls = row["calls"] if row else 0
            if user_calls >= max_calls_per_user_per_day:
                return False, "user_limit"

            conn.execute(
                """
                INSERT INTO llm_usage(day, user_id, calls)
                VALUES (?, ?, 1)
                ON CONFLICT(day, user_id) DO UPDATE SET calls = calls + 1
                """,
                (day, user_id),
            )
            return True, None

    def get_latest_encounter(self, actor_id: str, location_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(
                """
                SELECT encounter_id, actor_id, location_id, state_json
                FROM encounters
                WHERE actor_id = ? AND location_id = ?
                ORDER BY rowid DESC
                LIMIT 1
                """,
                (actor_id, location_id),
            ).fetchone()

    def get_arc_value(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.conn.execute("SELECT value_json FROM arc_state WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        try:
            value = json.loads(row["value_json"])
            return value if isinstance(value, dict) else None
        except Exception:
            return None

    def update_encounter_state(self, encounter_id: str, state: dict[str, Any]) -> None:
        with self.tx() as conn:
            conn.execute(
                "UPDATE encounters SET state_json = ? WHERE encounter_id = ?",
                (json.dumps(state, sort_keys=True), encounter_id),
            )

    def delete_encounter(self, encounter_id: str) -> None:
        with self.tx() as conn:
            conn.execute("DELETE FROM encounters WHERE encounter_id = ?", (encounter_id,))

    def delete_actor_encounters(self, actor_id: str, location_id: str | None = None) -> None:
        with self.tx() as conn:
            if location_id is None:
                conn.execute("DELETE FROM encounters WHERE actor_id = ?", (actor_id,))
            else:
                conn.execute(
                    "DELETE FROM encounters WHERE actor_id = ? AND location_id = ?",
                    (actor_id, location_id),
                )
