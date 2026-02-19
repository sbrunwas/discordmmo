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


def test_move_resolution_uses_location_alias(tmp_path):
    store = Store(str(tmp_path / "move_alias.db"))
    engine = WorldEngine(store, LLMClient(Settings(llm_backend="stub"), store=store), rng_seed=10)
    engine.initialize_world()
    assert engine.handle_message("p1", "Hero", "!start").ok
    move = engine.handle_message("p1", "Hero", "move to ruin")
    assert move.ok
    player = store.get_player("p1")
    assert player is not None
    assert player["location_id"] == "ruin_upper"


def test_first_visit_triggers_scene_description(tmp_path):
    store = Store(str(tmp_path / "visit_flag.db"))
    engine = WorldEngine(store, LLMClient(Settings(llm_backend="stub"), store=store), rng_seed=10)
    engine.initialize_world()
    assert engine.handle_message("p1", "Hero", "!start").ok
    assert not store.has_visited_location("p1", "ruin_upper")

    move = engine.handle_message("p1", "Hero", "move ruin")

    assert move.ok
    assert store.has_visited_location("p1", "ruin_upper")


def test_active_combat_state_is_handled(tmp_path):
    store = Store(str(tmp_path / "combat.db"))
    engine = WorldEngine(store, LLMClient(Settings(llm_backend="stub"), store=store), rng_seed=10)
    engine.initialize_world()
    assert engine.handle_message("p1", "Hero", "!start").ok
    encounter_id = trigger_combat(store, "p1", "town_square")

    response = engine.handle_message("p1", "Hero", "What is the danger?")

    assert response.ok
    assert "roll:" not in response.message
    assert "HP:" not in response.message
    assert "XP:" not in response.message
    assert encounter_id in store.conn.execute("SELECT encounter_id FROM encounters").fetchone()["encounter_id"]


def test_investigate_can_resolve_active_combat(tmp_path):
    store = Store(str(tmp_path / "combat_resolve.db"))
    engine = WorldEngine(store, LLMClient(Settings(llm_backend="stub"), store=store), rng_seed=10)
    engine.initialize_world()
    assert engine.handle_message("p1", "Hero", "!start").ok
    encounter_id = trigger_combat(store, "p1", "town_square")

    response = engine.handle_message("p1", "Hero", "investigate enemy")

    assert response.ok
    assert "roll:" not in response.message
    assert "HP:" not in response.message
    assert "XP:" not in response.message
    gone = store.conn.execute("SELECT encounter_id FROM encounters WHERE encounter_id = ?", (encounter_id,)).fetchone()
    assert gone is None


def test_other_players_combat_does_not_block_turn(tmp_path):
    store = Store(str(tmp_path / "combat_scope.db"))
    engine = WorldEngine(store, LLMClient(Settings(llm_backend="stub"), store=store), rng_seed=10)
    engine.initialize_world()
    assert engine.handle_message("p1", "Hero", "!start").ok
    assert engine.handle_message("p2", "Rival", "!start").ok
    trigger_combat(store, "p2", "town_square")

    response = engine.handle_message("p1", "Hero", "look")

    assert response.ok
    assert "Combat is active" not in response.message


def test_talk_to_npc_persists_dialogue_memory(tmp_path):
    store = Store(str(tmp_path / "npc_talk.db"))
    engine = WorldEngine(store, LLMClient(Settings(llm_backend="stub"), store=store), rng_seed=10)
    engine.initialize_world()
    assert engine.handle_message("p1", "Hero", "!start").ok

    response = engine.handle_message("p1", "Hero", "talk to scholar ione about the runes")

    assert response.ok
    assert not response.message.startswith("Scholar Ione:")
    memory_rows = store.conn.execute(
        "SELECT COUNT(*) AS c FROM npc_dialogue_memory WHERE npc_id = 'scholar_ione' AND player_id = 'p1'"
    ).fetchone()["c"]
    assert memory_rows >= 2


def test_documented_commands_return_specific_feedback(tmp_path):
    store = Store(str(tmp_path / "commands.db"))
    engine = WorldEngine(store, LLMClient(Settings(llm_backend="stub"), store=store), rng_seed=10)
    engine.initialize_world()
    assert engine.handle_message("p1", "Hero", "!start").ok

    factions = engine.handle_message("p1", "Hero", "!factions")
    recap = engine.handle_message("p1", "Hero", "!recap")
    skills = engine.handle_message("p1", "Hero", "!skills")

    assert "The stars do not answer" not in factions.message
    assert "timeline" in recap.message.lower()
    assert "prototype" in skills.message.lower()


def test_unknown_follow_up_continues_last_npc_dialogue(tmp_path):
    store = Store(str(tmp_path / "npc_followup.db"))
    engine = WorldEngine(store, LLMClient(Settings(llm_backend="stub"), store=store), rng_seed=10)
    engine.initialize_world()
    assert engine.handle_message("p1", "Hero", "!start").ok
    assert engine.handle_message("p1", "Hero", "talk to scholar ione").ok

    follow_up = engine.handle_message("p1", "Hero", "What do you think causes that?")

    assert follow_up.ok
    assert not follow_up.message.startswith("Scholar Ione:")


class FakeStoryClient:
    def complete_json(self, prompt: str, user_id: str = "system", **kwargs) -> dict:
        response_format = kwargs.get("response_format")
        if response_format is not None:
            if "Yes tell me more" in prompt:
                return {"action": "LOOK", "target": None, "confidence": 0.9, "clarify_question": None}
            return {"action": "TALK", "target": "traveler", "confidence": 0.9, "clarify_question": None}
        return {"text": "The road north is cursed after dusk, so caravans stay near the square fires."}


def test_dialogue_continues_when_intent_llm_returns_look(tmp_path):
    store = Store(str(tmp_path / "npc_look_followup.db"))
    engine = WorldEngine(store, FakeStoryClient(), rng_seed=10)
    engine.initialize_world()
    assert engine.handle_message("p1", "Hero", "!start").ok

    first = engine.handle_message("p1", "Hero", "talk traveler sera")
    second = engine.handle_message("p1", "Hero", "Yes tell me more")

    assert first.ok
    assert second.ok
    assert not second.message.startswith("Traveler Sera:")
