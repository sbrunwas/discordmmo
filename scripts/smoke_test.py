from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.db.store import Store
from app.engine.combat_engine import trigger_combat
from app.engine.world_engine import WorldEngine
from app.llm.client import LLMClient


def run() -> None:
    store = Store(":memory:")
    engine = WorldEngine(store, LLMClient(Settings(llm_json_backend="stub", llm_text_backend="stub"), store=store), rng_seed=17)
    engine.initialize_world()

    assert engine.handle_message("smoke", "Smoke", "!start").ok
    assert engine.handle_message("smoke", "Smoke", "look").ok
    assert engine.handle_message("smoke", "Smoke", "talk to scholar ione").ok
    before = store.get_npc_memory_json("scholar_ione").get("memory_summary", "")
    assert engine.handle_message("smoke", "Smoke", "talk to scholar ione can you help me").ok
    after = store.get_npc_memory_json("scholar_ione").get("memory_summary", "")
    assert len(after) >= len(before)
    assert engine.handle_message("smoke", "Smoke", "move ruin").ok
    assert engine.handle_message("smoke", "Smoke", "investigate sigil").ok
    engine.run_npc_planner_tick(now_ts=1_001_000, max_npcs=2)
    tick_events = store.conn.execute(
        "SELECT COUNT(*) AS c FROM events WHERE actor_id = 'system' AND event_type IN ('NPC_TICK', 'NPC_MOVED', 'FLAVOR_ONLY')"
    ).fetchone()["c"]
    assert tick_events >= 1
    encounter_id = trigger_combat(store, "smoke", "ruin_upper")
    assert encounter_id
    print("smoke_test_passed")


if __name__ == "__main__":
    run()
