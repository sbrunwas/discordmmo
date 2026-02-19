from __future__ import annotations

import json

from app.config import Settings
from app.db.store import Store
from app.engine.world_engine import WorldEngine
from app.llm.client import LLMClient


def _engine(tmp_path):
    store = Store(str(tmp_path / "npcforge.db"))
    client = LLMClient(Settings(llm_json_backend="stub", llm_text_backend="stub"), store=store)
    engine = WorldEngine(store, client, rng_seed=12)
    engine.initialize_world()
    return store, engine


def test_talk_twice_updates_npc_memory_summary(tmp_path):
    store, engine = _engine(tmp_path)
    assert engine.handle_message("p1", "Hero", "!start").ok
    assert engine.handle_message("p1", "Hero", "talk scholar ione").ok
    before = store.get_npc_memory_json("scholar_ione").get("memory_summary", "")
    assert engine.handle_message("p1", "Hero", "talk scholar ione can you help me").ok
    after = store.get_npc_memory_json("scholar_ione").get("memory_summary", "")
    assert len(after) >= len(before)
    assert "Spoke with p1" in after


def test_planner_tick_results_in_move_or_flavor_npc_tick_event(tmp_path):
    store, engine = _engine(tmp_path)
    acted = engine.run_npc_planner_tick(now_ts=999_999, max_npcs=2)
    assert acted >= 0
    rows = store.conn.execute(
        "SELECT event_type, payload_json FROM events WHERE actor_id = 'system' ORDER BY event_id DESC LIMIT 20"
    ).fetchall()
    saw_tick_effect = False
    for row in rows:
        payload = json.loads(row["payload_json"])
        tags = payload.get("tags", [])
        if row["event_type"] in {"NPC_MOVED", "FLAVOR_ONLY", "NPC_TICK"} and "npc_tick" in tags:
            saw_tick_effect = True
            break
    assert saw_tick_effect
