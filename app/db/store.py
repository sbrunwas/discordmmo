from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.db.schema import init_db

log = logging.getLogger(__name__)


class Store:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
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
        return self.conn.execute("SELECT * FROM players WHERE player_id = ?", (player_id,)).fetchone()

    def move_player(self, player_id: str, location_id: str) -> None:
        with self.tx() as conn:
            conn.execute("UPDATE players SET location_id=? WHERE player_id=?", (location_id, player_id))

    def upsert_location(self, location_id: str, name: str, description: str) -> None:
        with self.tx() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO locations(location_id, name, description) VALUES (?, ?, ?)",
                (location_id, name, description),
            )

    def get_location(self, location_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM locations WHERE location_id=?", (location_id,)).fetchone()

    def set_arc_value(self, key: str, value: dict[str, Any]) -> None:
        with self.tx() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO arc_state(key, value_json) VALUES (?, ?)",
                (key, json.dumps(value, sort_keys=True)),
            )

    def upsert_npc(self, npc_id: str, name: str, location_id: str, is_key: bool = False, alive: bool = True) -> None:
        with self.tx() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO npcs(npc_id, name, location_id, is_key, alive)
                VALUES (?, ?, ?, ?, ?)
                """,
                (npc_id, name, location_id, 1 if is_key else 0, 1 if alive else 0),
            )

    def list_npcs_at_location(self, location_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT npc_id, name, location_id, is_key, alive FROM npcs WHERE location_id = ? AND alive = 1 ORDER BY name",
            (location_id,),
        ).fetchall()

    def upsert_npc_profile(self, npc_id: str, persona_prompt: str) -> None:
        with self.tx() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO npc_profiles(npc_id, persona_prompt) VALUES (?, ?)",
                (npc_id, persona_prompt),
            )

    def get_npc_profile(self, npc_id: str) -> sqlite3.Row | None:
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

    def add_proposal(self, actor_id: str, proposal_type: str, content: str) -> None:
        with self.tx() as conn:
            conn.execute(
                "INSERT INTO proposals(actor_id, proposal_type, content) VALUES (?, ?, ?)",
                (actor_id, proposal_type, content),
            )

    def get_recent_events(self, actor_id: str, limit: int = 6) -> list[dict[str, Any]]:
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

    def get_latest_encounter(self, location_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            """
            SELECT encounter_id, location_id, state_json
            FROM encounters
            WHERE location_id = ?
            ORDER BY rowid DESC
            LIMIT 1
            """,
            (location_id,),
        ).fetchone()

    def update_encounter_state(self, encounter_id: str, state: dict[str, Any]) -> None:
        with self.tx() as conn:
            conn.execute(
                "UPDATE encounters SET state_json = ? WHERE encounter_id = ?",
                (json.dumps(state, sort_keys=True), encounter_id),
            )

    def delete_encounter(self, encounter_id: str) -> None:
        with self.tx() as conn:
            conn.execute("DELETE FROM encounters WHERE encounter_id = ?", (encounter_id,))
