from __future__ import annotations

import json
import logging
import random

from app.db.store import Store
from app.engine.arc_engine import initialize_arc
from app.engine.combat_engine import trigger_combat
from app.llm.npc_dialogue import generate_npc_reply
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
        self._seed_npcs()
        self.store.write_event("system", "WORLD_INITIALIZED", {"locations": 2})

    def handle_message(self, actor_id: str, actor_name: str, text: str) -> ActionResult:
        log.info("discord_message_received actor=%s text=%s", actor_id, text)
        player = self.store.get_player(actor_id)
        context = self._intent_context(actor_id, player)
        intent = parse_intent(text, llm_client=self.narrator_client, user_id=actor_id, context=context)
        if intent.action == "HELP":
            return ActionResult(
                True,
                "Commands: !help !start !stats !inventory !skills !respec !factions !recap !rest short !rest long !duel\n"
                f"{self._exploration_prompt()}",
            )
        if intent.action == "START":
            self.store.create_player(actor_id, actor_name, "town_square")
            self.store.write_event(actor_id, "PLAYER_STARTED", {"name": actor_name})
            return ActionResult(True, f"Your journey begins in Asterfall Commons.\n{self._exploration_prompt()}")

        if player is None:
            return ActionResult(False, "Use !start first.")

        encounter_row = self.store.get_latest_encounter(player["location_id"])
        if encounter_row is not None:
            return self._handle_active_combat(actor_id, player["location_id"], intent, encounter_row)

        if intent.action == "LOOK":
            loc = self.store.get_location(player["location_id"])
            scene = loc["description"] if loc else "The world flickers uncertainly."
            text = narrate(self.narrator_client, scene, "look", user_id=actor_id)
            return ActionResult(True, f"{text}\n\n{self._exploration_prompt()}")
        if intent.action == "MOVE":
            target = "ruin_upper" if (intent.target and "ruin" in intent.target) else "town_square"
            self.store.move_player(actor_id, target)
            self.store.write_event(actor_id, "PLAYER_MOVED", {"to": target})
            return ActionResult(True, f"You move to {target}.\n{self._exploration_prompt(target)}")
        if intent.action == "TALK":
            return self._handle_talk(actor_id, text, player["location_id"], intent.target)
        if intent.action == "INVESTIGATE":
            roll = self.rng.randint(1, 20)
            payload = {"roll": roll, "discovery": "constellation sigil" if roll >= 10 else "old mortar dust"}
            self.store.write_event(actor_id, "INVESTIGATED", payload)
            if roll >= 15:
                encounter = trigger_combat(self.store, player["location_id"])
                return ActionResult(True, f"You uncover danger. Combat starts: {encounter}\n{self._combat_prompt()}")
            return ActionResult(True, f"You investigate and find {payload['discovery']}.\n{self._exploration_prompt()}")
        if intent.action in {"REST_SHORT", "REST_LONG"}:
            self.store.write_event(actor_id, intent.action, {})
            return ActionResult(True, f"You take time to recover.\n{self._exploration_prompt()}")
        return ActionResult(
            True,
            "The stars do not answer that action yet.\n"
            f"{self._exploration_prompt()}",
        )

    def _intent_context(self, actor_id: str, player) -> dict:
        context: dict[str, object] = {
            "known_actions": ["LOOK", "MOVE", "INVESTIGATE", "TALK", "REST_SHORT", "REST_LONG", "HELP", "START"],
            "recent_events": self.store.get_recent_events(actor_id, limit=6),
        }
        if player is None:
            context["player_started"] = False
            return context
        context["player_started"] = True
        location = self.store.get_location(player["location_id"])
        if location is not None:
            context["location"] = {
                "id": location["location_id"],
                "name": location["name"],
                "description": location["description"],
            }
            context["nearby_npcs"] = [row["name"] for row in self.store.list_npcs_at_location(location["location_id"])]
        return context

    def _handle_active_combat(self, actor_id: str, location_id: str, intent, encounter_row) -> ActionResult:
        state = json.loads(encounter_row["state_json"])
        encounter_id = encounter_row["encounter_id"]
        enemy_role = state.get("enemy_role", "threat")
        turn = int(state.get("turn", 1))

        if intent.action in {"LOOK", "UNKNOWN"}:
            return ActionResult(
                True,
                f"Combat is active against a {enemy_role} (turn {turn}). "
                f"{self._combat_prompt()}",
            )

        if intent.action == "MOVE":
            self.store.delete_encounter(encounter_id)
            self.store.write_event(actor_id, "COMBAT_DISENGAGED", {"encounter_id": encounter_id, "location_id": location_id})
            return ActionResult(True, f"You break away and disengage from combat.\n{self._exploration_prompt(location_id)}")

        if intent.action == "INVESTIGATE":
            roll = self.rng.randint(1, 20)
            if roll >= 10:
                self.store.delete_encounter(encounter_id)
                self.store.write_event(
                    actor_id,
                    "COMBAT_RESOLVED",
                    {"encounter_id": encounter_id, "location_id": location_id, "roll": roll, "result": "won"},
                )
                return ActionResult(True, f"You outmaneuver the {enemy_role} and end the fight.\n{self._exploration_prompt(location_id)}")

            state["turn"] = turn + 1
            self.store.update_encounter_state(encounter_id, state)
            self.store.write_event(
                actor_id,
                "COMBAT_PROGRESS",
                {"encounter_id": encounter_id, "location_id": location_id, "roll": roll, "turn": state["turn"]},
            )
            return ActionResult(True, f"The {enemy_role} presses in. Combat continues (turn {state['turn']}).")

        return ActionResult(
            True,
            f"Combat is active. {self._combat_prompt()}",
        )

    def _exploration_prompt(self, location_id: str = "town_square") -> str:
        if location_id == "ruin_upper":
            return "Try: `look`, `investigate sigil`, `talk warden lyra`, `move town`, `rest short`, or `!help`."
        return "Try: `look`, `talk quartermaster brann`, `talk scholar ione`, `talk traveler sera`, `move ruin`, `rest short`, or `!help`."

    def _combat_prompt(self) -> str:
        return "Try: `investigate` to engage carefully, `move` to disengage, or `look` for status."

    def _seed_npcs(self) -> None:
        self.store.upsert_npc("quartermaster_brann", "Quartermaster Brann", "town_square", is_key=True)
        self.store.upsert_npc("scholar_ione", "Scholar Ione", "town_square", is_key=True)
        self.store.upsert_npc("traveler_sera", "Traveler Sera", "town_square", is_key=False)
        self.store.upsert_npc("warden_lyra", "Warden Lyra", "ruin_upper", is_key=True)
        self.store.upsert_npc_profile(
            "quartermaster_brann",
            "Gruff ex-mercenary quartermaster. Practical, blunt, unexpectedly kind to new adventurers. "
            "Always references supply shortages, local rumors, and tactical caution.",
        )
        self.store.upsert_npc_profile(
            "scholar_ione",
            "Curious ruin scholar obsessed with celestial inscriptions. Speaks quickly, asks follow-up questions, "
            "and connects current events to ancient lore.",
        )
        self.store.upsert_npc_profile(
            "warden_lyra",
            "Calm ruin warden with a guarded tone. Protective of the chamber and sensitive to magical disturbances. "
            "Encourages discipline and careful observation.",
        )
        self.store.upsert_npc_profile(
            "traveler_sera",
            "Friendly roadworn scout who shares rumors, campfire stories, and practical travel advice. "
            "Warm and conversational, but wary about dangerous ruins.",
        )

    def _handle_talk(self, actor_id: str, player_text: str, location_id: str, target: str | None) -> ActionResult:
        npcs = self.store.list_npcs_at_location(location_id)
        if not npcs:
            return ActionResult(True, "No one here is available to talk right now.")

        npc = self._select_npc(npcs, target)
        if npc is None:
            available = ", ".join(row["name"] for row in npcs)
            return ActionResult(True, f"I couldn't tell who you meant. Try one of: {available}.")

        profile = self.store.get_npc_profile(npc["npc_id"])
        persona = profile["persona_prompt"] if profile else f"{npc['name']} is a local resident."
        location = self.store.get_location(location_id)
        history = self.store.get_npc_dialogue_history(npc["npc_id"], actor_id, limit=10)
        reply = generate_npc_reply(
            self.narrator_client,
            user_id=actor_id,
            npc_name=npc["name"],
            npc_persona=persona,
            location_name=location["name"] if location else "Unknown",
            location_description=location["description"] if location else "",
            player_message=player_text,
            history=history,
        )
        self.store.append_npc_dialogue(npc["npc_id"], actor_id, "player", player_text)
        self.store.append_npc_dialogue(npc["npc_id"], actor_id, "npc", reply)
        self.store.write_event(actor_id, "NPC_DIALOGUE", {"npc_id": npc["npc_id"], "location_id": location_id})
        return ActionResult(True, f"{npc['name']}: {reply}\n{self._exploration_prompt(location_id)}")

    def _select_npc(self, npcs, target: str | None):
        if not target:
            return npcs[0]
        lower = target.lower()
        keyword_map = {
            "traveler": "traveler",
            "travellers": "traveler",
            "scholar": "scholar",
            "merchant": "quartermaster",
            "quartermaster": "quartermaster",
            "warden": "warden",
        }
        for key, hint in keyword_map.items():
            if key in lower:
                for npc in npcs:
                    if hint in npc["name"].lower():
                        return npc
        for npc in npcs:
            if lower in npc["name"].lower():
                return npc
        for npc in npcs:
            tokens = npc["name"].lower().split()
            if any(token in lower for token in tokens):
                return npc
        return None
