from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.store import Store
from app.engine.combat_engine import trigger_combat
from app.engine.world_engine import WorldEngine
from app.llm.client import LLMClient


def run() -> None:
    store = Store(":memory:")
    engine = WorldEngine(store, LLMClient(None), rng_seed=17)
    engine.initialize_world()

    assert engine.handle_message("smoke", "Smoke", "!start").ok
    assert engine.handle_message("smoke", "Smoke", "look").ok
    assert engine.handle_message("smoke", "Smoke", "move ruin").ok
    assert engine.handle_message("smoke", "Smoke", "investigate sigil").ok
    encounter_id = trigger_combat(store, "ruin_upper")
    assert encounter_id
    print("smoke_test_passed")


if __name__ == "__main__":
    run()
