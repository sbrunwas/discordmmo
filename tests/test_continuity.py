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
    assert response.message
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


class CaptureNarrationClient:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete_json(self, prompt: str, user_id: str = "system", **kwargs) -> dict:
        response_format = kwargs.get("response_format")
        if response_format is not None:
            return {"action": "LOOK", "target": None, "confidence": 0.9, "clarify_question": None}
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            return {"text": "You study the square while the crowd moves around the old stones."}
        return {"text": "You notice details you missed before, the same plaza now seen from a sharper angle."}


def test_repeated_look_passes_last_narration_to_client(tmp_path):
    store = Store(str(tmp_path / "look_history.db"))
    client = CaptureNarrationClient()
    engine = WorldEngine(store, client, rng_seed=10)
    engine.initialize_world()
    assert engine.handle_message("p1", "Hero", "!start").ok

    first = engine.handle_message("p1", "Hero", "look")
    second = engine.handle_message("p1", "Hero", "look")

    assert first.ok and second.ok
    assert len(client.prompts) >= 2
    assert "last_narration" in client.prompts[1]
    assert "You study the square while the crowd moves around the old stones." in client.prompts[1]
