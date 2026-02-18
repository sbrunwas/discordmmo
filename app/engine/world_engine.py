from __future__ import annotations

import logging
import random

from app.db.store import Store
from app.engine.arc_engine import initialize_arc
from app.engine.combat_engine import trigger_combat
from app.llm.intent_parser import parse_intent
from app.llm.narrator import narrate
from app.models.core import ActionResult

log = logging.getLogger(__name__)


class WorldEngine:
    def __init__(self, store: Store, narrator_client, rng_seed: int = 1337) -> None:
        self.store = store
        self.narrator_client = narrator_client
        self.rng = random.Random(rng_seed)

    def initialize_world(self) -> None:
        self.store.upsert_location(
            "town_square",
            "Asterfall Commons",
            "A warm tavern square built atop a half-exposed celestial ruin.",
        )
        self.store.upsert_location(
            "ruin_upper",
            "Upper Chamber",
            "Dusty star-metal plates hum beneath the stone.",
        )
        initialize_arc(self.store)
        self.store.write_event("system", "WORLD_INITIALIZED", {"locations": 2})

    def handle_message(self, actor_id: str, actor_name: str, text: str) -> ActionResult:
        log.info("discord_message_received actor=%s text=%s", actor_id, text)
        intent = parse_intent(text)
        if intent.action == "HELP":
            return ActionResult(True, "Commands: !help !start !stats !inventory !skills !respec !factions !recap !rest short !rest long !duel")
        if intent.action == "START":
            self.store.create_player(actor_id, actor_name, "town_square")
            self.store.write_event(actor_id, "PLAYER_STARTED", {"name": actor_name})
            return ActionResult(True, "Your journey begins in Asterfall Commons.")

        player = self.store.get_player(actor_id)
        if player is None:
            return ActionResult(False, "Use !start first.")

        if intent.action == "LOOK":
            loc = self.store.get_location(player["location_id"])
            scene = loc["description"] if loc else "The world flickers uncertainly."
            return ActionResult(True, narrate(self.narrator_client, scene, "look"))
        if intent.action == "MOVE":
            target = "ruin_upper" if (intent.target and "ruin" in intent.target) else "town_square"
            self.store.move_player(actor_id, target)
            self.store.write_event(actor_id, "PLAYER_MOVED", {"to": target})
            return ActionResult(True, f"You move to {target}.")
        if intent.action == "INVESTIGATE":
            roll = self.rng.randint(1, 20)
            payload = {"roll": roll, "discovery": "constellation sigil" if roll >= 10 else "old mortar dust"}
            self.store.write_event(actor_id, "INVESTIGATED", payload)
            if roll >= 15:
                encounter = trigger_combat(self.store, player["location_id"])
                return ActionResult(True, f"You uncover danger. Combat starts: {encounter}")
            return ActionResult(True, f"You investigate and find {payload['discovery']}.")
        if intent.action in {"REST_SHORT", "REST_LONG"}:
            self.store.write_event(actor_id, intent.action, {})
            return ActionResult(True, "You take time to recover.")
        return ActionResult(True, "The stars do not answer that action yet.")
