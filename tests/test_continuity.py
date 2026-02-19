from __future__ import annotations

import logging

from app.config import Settings
from app.db.store import Store
from app.engine.world_engine import WorldEngine
from app.llm.client import LLMClient


def _engine(tmp_path):
    store = Store(str(tmp_path / "continuity.db"))
    engine = WorldEngine(store, LLMClient(Settings(llm_backend="stub"), store=store), rng_seed=10)
    engine.initialize_world()
    return store, engine


def test_confidence_gate_returns_clarification(tmp_path):
    store, engine = _engine(tmp_path)
    assert engine.handle_message("p1", "Hero", "!start").ok

    response = engine.handle_message("p1", "Hero", "could you maybe do something")

    assert response.ok
    assert "basic parser" in response.message.lower()
    assert store.get_session_state("p1")["mode"] == "explore"


def test_anti_loop_adds_progression_nudge(tmp_path):
    _, engine = _engine(tmp_path)
    first = engine.handle_message("p1", "Hero", "!help")
    second = engine.handle_message("p1", "Hero", "!help")

    assert first.ok and second.ok
    assert "New development:" in second.message


def test_scene_memory_and_threads_are_persisted(tmp_path):
    store, engine = _engine(tmp_path)
    assert engine.handle_message("p1", "Hero", "!start").ok
    assert engine.handle_message("p1", "Hero", "move ruin").ok

    scene = store.get_scene_memory("p1")
    assert scene["mode"] == "explore"
    assert scene["location_id"] == "ruin_upper"
    assert scene["active_thread_id"] == "travel:ruin_upper"
    thread = store.conn.execute(
        "SELECT thread_id FROM player_threads WHERE player_id = ? AND thread_id = ?",
        ("p1", "travel:ruin_upper"),
    ).fetchone()
    assert thread is not None


def test_npc_summary_is_updated(tmp_path):
    store, engine = _engine(tmp_path)
    assert engine.handle_message("p1", "Hero", "!start").ok
    assert engine.handle_message("p1", "Hero", "talk scholar ione").ok

    summary = store.get_npc_dialogue_summary("scholar_ione", "p1")

    assert summary
    assert "Player asked:" in summary


def test_observability_log_includes_mode_and_thread(tmp_path, caplog):
    _, engine = _engine(tmp_path)
    with caplog.at_level(logging.INFO):
        engine.handle_message("p1", "Hero", "!start")

    logs = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "turn_resolved" in logs
    assert "mode_before" in logs
    assert "thread=" in logs
