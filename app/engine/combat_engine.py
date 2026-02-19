from __future__ import annotations

import json
import uuid

from app.db.store import Store


def trigger_combat(store: Store, actor_id: str, location_id: str) -> str:
    encounter_id = str(uuid.uuid4())
    payload = {"zone": ["front", "mid", "rear"], "enemy_role": "skirmisher", "turn": 1}
    with store.tx() as conn:
        conn.execute(
            "INSERT INTO encounters(encounter_id, actor_id, location_id, state_json) VALUES (?, ?, ?, ?)",
            (encounter_id, actor_id, location_id, json.dumps(payload, sort_keys=True)),
        )
    store.write_event(actor_id, "COMBAT_TRIGGERED", {"encounter_id": encounter_id, "location_id": location_id})
    return encounter_id
