from app.db.store import Store
from app.engine.world_engine import WorldEngine
from app.llm.client import LLMClient


def test_start_and_move_persists(tmp_path):
    store = Store(str(tmp_path / "test.db"))
    engine = WorldEngine(store, LLMClient(None), rng_seed=10)
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
