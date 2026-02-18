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

    def add_proposal(self, actor_id: str, proposal_type: str, content: str) -> None:
        with self.tx() as conn:
            conn.execute(
                "INSERT INTO proposals(actor_id, proposal_type, content) VALUES (?, ?, ?)",
                (actor_id, proposal_type, content),
            )
