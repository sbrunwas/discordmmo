from app.config import Settings
from app.db.store import Store
from app.engine.combat_engine import trigger_combat
from app.engine.world_engine import WorldEngine
from app.llm.client import LLMClient


def test_start_and_move_persists(tmp_path):
    store = Store(str(tmp_path / "test.db"))
    engine = WorldEngine(store, LLMClient(Settings(llm_backend="stub"), store=store), rng_seed=10)
    engine.initialize_world()

    start = engine.handle_message("p1", "Hero", "!start")
    assert start.ok
    move = engine.handle_message("p1", "Hero", "move ruin")
    assert move.ok

    player = store.get_player("p1")
    assert player is not None
    assert player["location_id"] == "ruin_upper"

    count = store.conn.execute("SELECT COUNT(*) c FROM events WHERE actor_id='p1'").fetchone()["c"]
    assert count >= 2


def test_active_combat_state_is_handled(tmp_path):
    store = Store(str(tmp_path / "combat.db"))
    engine = WorldEngine(store, LLMClient(Settings(llm_backend="stub"), store=store), rng_seed=10)
    engine.initialize_world()
    assert engine.handle_message("p1", "Hero", "!start").ok
    encounter_id = trigger_combat(store, "town_square")

    response = engine.handle_message("p1", "Hero", "What is the danger?")

    assert response.ok
    assert "Combat is active" in response.message
    assert encounter_id in store.conn.execute("SELECT encounter_id FROM encounters").fetchone()["encounter_id"]


def test_investigate_can_resolve_active_combat(tmp_path):
    store = Store(str(tmp_path / "combat_resolve.db"))
    engine = WorldEngine(store, LLMClient(Settings(llm_backend="stub"), store=store), rng_seed=10)
    engine.initialize_world()
    assert engine.handle_message("p1", "Hero", "!start").ok
    encounter_id = trigger_combat(store, "town_square")

    response = engine.handle_message("p1", "Hero", "investigate enemy")

    assert response.ok
    assert "end the fight" in response.message
    gone = store.conn.execute("SELECT encounter_id FROM encounters WHERE encounter_id = ?", (encounter_id,)).fetchone()
    assert gone is None


def test_talk_to_npc_persists_dialogue_memory(tmp_path):
    store = Store(str(tmp_path / "npc_talk.db"))
    engine = WorldEngine(store, LLMClient(Settings(llm_backend="stub"), store=store), rng_seed=10)
    engine.initialize_world()
    assert engine.handle_message("p1", "Hero", "!start").ok

    response = engine.handle_message("p1", "Hero", "talk to scholar ione about the runes")

    assert response.ok
    assert "Scholar Ione:" in response.message
    memory_rows = store.conn.execute(
        "SELECT COUNT(*) AS c FROM npc_dialogue_memory WHERE npc_id = 'scholar_ione' AND player_id = 'p1'"
    ).fetchone()["c"]
    assert memory_rows >= 2
