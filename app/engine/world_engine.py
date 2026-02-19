from __future__ import annotations

import json
import logging
import random
import re

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
        session = self.store.get_session_state(actor_id)
        mode_before = session["mode"]
        player = self.store.get_player(actor_id)
        context = self._intent_context(actor_id, player)
        intent = parse_intent(text, llm_client=self.narrator_client, user_id=actor_id, context=context)
        if intent.action == "HELP":
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="explore",
                action="HELP",
                message=(
                    "Commands: !help !start !stats !inventory !skills !respec !factions !recap !rest short !rest long !duel\n"
                    f"{self._exploration_prompt()}"
                ),
                player=player,
                thread_id=session.get("active_thread_id"),
            )
        if intent.action == "START":
            self.store.create_player(actor_id, actor_name, "town_square")
            self.store.write_event(actor_id, "PLAYER_STARTED", {"name": actor_name})
            player = self.store.get_player(actor_id)
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="explore",
                action="START",
                message=f"Your journey begins in Asterfall Commons.\n{self._exploration_prompt()}",
                player=player,
                thread_id="thread:intro",
            )

        if player is None:
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="explore",
                action="UNKNOWN",
                message="Use !start first.",
                player=player,
                thread_id=session.get("active_thread_id"),
                ok=False,
            )

        encounter_row = self.store.get_latest_encounter(actor_id, player["location_id"])
        if encounter_row is not None:
            combat = self._handle_active_combat(actor_id, player["location_id"], intent, encounter_row)
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after=combat["mode_after"],
                action=intent.action,
                message=combat["message"],
                player=player,
                thread_id=combat["thread_id"],
                active_npc_id=None,
                active_encounter_id=combat["active_encounter_id"],
            )

        npc_target = self._active_dialogue_npc_target(actor_id, player["location_id"])
        if npc_target is not None and self._should_continue_dialogue(text, intent.action):
            talk = self._handle_talk(actor_id, text, player["location_id"], npc_target)
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="dialogue",
                action="TALK",
                message=talk["message"],
                player=player,
                thread_id=talk["thread_id"],
                active_npc_id=talk["npc_id"],
            )

        if intent.action == "UNKNOWN" and intent.confidence < 0.45:
            clarification = intent.clarify_question or "I am not sure what you want to do. Try `!help`."
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after=session["mode"],
                action=intent.action,
                message=clarification,
                player=player,
                thread_id=session.get("active_thread_id"),
                ok=True,
            )

        if intent.action == "LOOK":
            loc = self.store.get_location(player["location_id"])
            scene = loc["description"] if loc else "The world flickers uncertainly."
            text = narrate(self.narrator_client, scene, "look", user_id=actor_id)
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="explore",
                action="LOOK",
                message=f"{text}\n\n{self._exploration_prompt(player['location_id'])}",
                player=player,
                thread_id=session.get("active_thread_id"),
                active_npc_id=None,
            )
        if intent.action == "MOVE":
            target = "ruin_upper" if (intent.target and "ruin" in intent.target) else "town_square"
            self.store.move_player(actor_id, target)
            self.store.write_event(actor_id, "PLAYER_MOVED", {"to": target})
            player = self.store.get_player(actor_id)
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="explore",
                action="MOVE",
                message=f"You move to {target}.\n{self._exploration_prompt(target)}",
                player=player,
                thread_id=f"travel:{target}",
                active_npc_id=None,
                active_encounter_id=None,
            )
        if intent.action == "TALK":
            talk = self._handle_talk(actor_id, text, player["location_id"], intent.target)
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="dialogue",
                action="TALK",
                message=talk["message"],
                player=player,
                thread_id=talk["thread_id"],
                active_npc_id=talk["npc_id"],
            )
        if intent.action == "INVESTIGATE":
            roll = self.rng.randint(1, 20)
            payload = {"roll": roll, "discovery": "constellation sigil" if roll >= 10 else "old mortar dust"}
            self.store.write_event(actor_id, "INVESTIGATED", payload)
            if roll >= 15:
                encounter = trigger_combat(self.store, actor_id, player["location_id"])
                return self._respond(
                    actor_id,
                    session=session,
                    mode_before=mode_before,
                    mode_after="combat",
                    action="INVESTIGATE",
                    message=f"You uncover danger. Combat starts: {encounter}\n{self._combat_prompt()}",
                    player=player,
                    thread_id=f"combat:{encounter}",
                    active_npc_id=None,
                    active_encounter_id=encounter,
                )
            discovery_thread = "mystery:constellation_sigil" if payload["discovery"] == "constellation sigil" else "mystery:ruin_dust"
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="explore",
                action="INVESTIGATE",
                message=f"You investigate and find {payload['discovery']}.\n{self._exploration_prompt(player['location_id'])}",
                player=player,
                thread_id=discovery_thread,
                active_npc_id=None,
            )
        if intent.action in {"REST_SHORT", "REST_LONG"}:
            self.store.write_event(actor_id, intent.action, {})
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="explore",
                action=intent.action,
                message=f"You take time to recover.\n{self._exploration_prompt(player['location_id'])}",
                player=player,
                thread_id=session.get("active_thread_id"),
                active_npc_id=None,
            )
        return self._respond(
            actor_id,
            session=session,
            mode_before=mode_before,
            mode_after="explore",
            action=intent.action,
            message="The stars do not answer that action yet.\n"
            f"{self._exploration_prompt(player['location_id'])}",
            player=player,
            thread_id=session.get("active_thread_id"),
            active_npc_id=None,
        )

    def _intent_context(self, actor_id: str, player) -> dict:
        context: dict[str, object] = {
            "known_actions": ["LOOK", "MOVE", "INVESTIGATE", "TALK", "REST_SHORT", "REST_LONG", "HELP", "START"],
            "recent_events": self.store.get_recent_events(actor_id, limit=6),
            "scene_memory": self.store.get_scene_memory(actor_id),
            "session_state": self.store.get_session_state(actor_id),
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

    def _handle_active_combat(self, actor_id: str, location_id: str, intent, encounter_row) -> dict[str, str | None]:
        state = json.loads(encounter_row["state_json"])
        encounter_id = encounter_row["encounter_id"]
        enemy_role = state.get("enemy_role", "threat")
        turn = int(state.get("turn", 1))

        if intent.action in {"LOOK", "UNKNOWN"}:
            return {
                "message": f"Combat is active against a {enemy_role} (turn {turn}). {self._combat_prompt()}",
                "mode_after": "combat",
                "thread_id": f"combat:{encounter_id}",
                "active_encounter_id": encounter_id,
            }

        if intent.action == "MOVE":
            self.store.delete_actor_encounters(actor_id, location_id)
            self.store.write_event(actor_id, "COMBAT_DISENGAGED", {"encounter_id": encounter_id, "location_id": location_id})
            return {
                "message": f"You break away and disengage from combat.\n{self._exploration_prompt(location_id)}",
                "mode_after": "explore",
                "thread_id": f"travel:{location_id}",
                "active_encounter_id": None,
            }

        if intent.action == "INVESTIGATE":
            roll = self.rng.randint(1, 20)
            if roll >= 10:
                self.store.delete_actor_encounters(actor_id, location_id)
                self.store.write_event(
                    actor_id,
                    "COMBAT_RESOLVED",
                    {"encounter_id": encounter_id, "location_id": location_id, "roll": roll, "result": "won"},
                )
                return {
                    "message": f"You outmaneuver the {enemy_role} and end the fight.\n{self._exploration_prompt(location_id)}",
                    "mode_after": "explore",
                    "thread_id": f"travel:{location_id}",
                    "active_encounter_id": None,
                }

            state["turn"] = turn + 1
            self.store.update_encounter_state(encounter_id, state)
            self.store.write_event(
                actor_id,
                "COMBAT_PROGRESS",
                {"encounter_id": encounter_id, "location_id": location_id, "roll": roll, "turn": state["turn"]},
            )
            return {
                "message": f"The {enemy_role} presses in. Combat continues (turn {state['turn']}).",
                "mode_after": "combat",
                "thread_id": f"combat:{encounter_id}",
                "active_encounter_id": encounter_id,
            }

        return {
            "message": f"Combat is active. {self._combat_prompt()}",
            "mode_after": "combat",
            "thread_id": f"combat:{encounter_id}",
            "active_encounter_id": encounter_id,
        }

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

    def _handle_talk(self, actor_id: str, player_text: str, location_id: str, target: str | None) -> dict[str, str]:
        npcs = self.store.list_npcs_at_location(location_id)
        if not npcs:
            return {"message": "No one here is available to talk right now.", "npc_id": "", "thread_id": "thread:none"}

        npc = self._select_npc(npcs, target)
        if npc is None:
            available = ", ".join(row["name"] for row in npcs)
            return {"message": f"I couldn't tell who you meant. Try one of: {available}.", "npc_id": "", "thread_id": "thread:none"}

        profile = self.store.get_npc_profile(npc["npc_id"])
        persona = profile["persona_prompt"] if profile else f"{npc['name']} is a local resident."
        location = self.store.get_location(location_id)
        history = self.store.get_npc_dialogue_history(npc["npc_id"], actor_id, limit=10)
        summary = self.store.get_npc_dialogue_summary(npc["npc_id"], actor_id)
        thread_id = f"npc:{npc['npc_id']}"
        reply = generate_npc_reply(
            self.narrator_client,
            user_id=actor_id,
            npc_name=npc["name"],
            npc_persona=persona,
            location_name=location["name"] if location else "Unknown",
            location_description=location["description"] if location else "",
            player_message=player_text,
            history=history,
            summary=summary,
            active_thread=thread_id,
        )
        self.store.append_npc_dialogue(npc["npc_id"], actor_id, "player", player_text)
        self.store.append_npc_dialogue(npc["npc_id"], actor_id, "npc", reply)
        self.store.upsert_npc_dialogue_summary(
            npc["npc_id"],
            actor_id,
            self._build_npc_summary(summary, player_text, reply),
        )
        self.store.write_event(actor_id, "NPC_DIALOGUE", {"npc_id": npc["npc_id"], "location_id": location_id})
        self.store.upsert_thread(
            actor_id,
            thread_id,
            "npc_dialogue",
            f"Conversation with {npc['name']}",
            reply,
            status="ACTIVE",
        )
        return {"message": f"{npc['name']}: {reply}\n{self._exploration_prompt(location_id)}", "npc_id": npc["npc_id"], "thread_id": thread_id}

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

    def _active_dialogue_npc_target(self, actor_id: str, location_id: str) -> str | None:
        recent = self.store.get_recent_events(actor_id, limit=4)
        for event in reversed(recent):
            if event["event_type"] != "NPC_DIALOGUE":
                continue
            payload = event.get("payload", {})
            if payload.get("location_id") != location_id:
                continue
            npc_id = payload.get("npc_id")
            if not isinstance(npc_id, str):
                continue
            npc = self.store.get_npc(npc_id)
            if npc is None:
                continue
            return str(npc["name"])
        return None

    def _should_continue_dialogue(self, text: str, action: str) -> bool:
        if action not in {"UNKNOWN", "LOOK"}:
            return False
        lower = text.strip().lower()
        if not lower:
            return False
        if lower.startswith("!"):
            return False
        if lower == "look":
            return False
        blocked_prefixes = ("move", "go ", "rest", "investigate", "talk ")
        if any(lower.startswith(prefix) for prefix in blocked_prefixes):
            return False
        # "where do I go" should not be forced into NPC conversation.
        if re.search(r"\b(move|go|rest|investigate)\b", lower):
            return False
        return True

    def _build_npc_summary(self, previous: str, player_text: str, npc_reply: str) -> str:
        base = previous.strip()
        addition = f" Player asked: {player_text.strip()} NPC replied: {npc_reply.strip()}"
        merged = (base + addition).strip()
        return merged[:600]

    def _respond(
        self,
        actor_id: str,
        *,
        session: dict,
        mode_before: str,
        mode_after: str,
        action: str,
        message: str,
        player,
        thread_id: str | None,
        ok: bool = True,
        active_npc_id: str | None = None,
        active_encounter_id: str | None = None,
    ) -> ActionResult:
        final_message, repeat_count = self._apply_anti_loop(session, message)
        self.store.upsert_session_state(
            actor_id,
            mode=mode_after,
            active_npc_id=active_npc_id,
            active_encounter_id=active_encounter_id,
            active_thread_id=thread_id,
            last_bot_message=final_message,
            repeat_count=repeat_count,
        )
        if thread_id:
            thread_type = thread_id.split(":", 1)[0]
            self.store.upsert_thread(
                actor_id,
                thread_id,
                thread_type,
                thread_id.replace(":", " ").title(),
                final_message,
                status="ACTIVE",
            )
        self.store.upsert_scene_memory(actor_id, self._scene_memory_snapshot(mode_after, action, player, thread_id, final_message))
        log.info(
            "turn_resolved actor=%s mode_before=%s intent=%s mode_after=%s thread=%s",
            actor_id,
            mode_before,
            action,
            mode_after,
            thread_id,
        )
        return ActionResult(ok, final_message)

    def _scene_memory_snapshot(self, mode: str, action: str, player, thread_id: str | None, message: str) -> dict:
        location_id = player["location_id"] if player is not None else None
        return {
            "mode": mode,
            "last_action": action,
            "location_id": location_id,
            "active_thread_id": thread_id,
            "last_message_excerpt": message[:220],
        }

    def _apply_anti_loop(self, session: dict, message: str) -> tuple[str, int]:
        normalized_current = " ".join(message.lower().split())
        normalized_previous = " ".join(str(session.get("last_bot_message", "")).lower().split())
        repeat_count = int(session.get("repeat_count", 0))
        if normalized_current and normalized_current == normalized_previous:
            repeat_count += 1
        else:
            repeat_count = 0
        if repeat_count >= 1:
            message = (
                f"{message}\n\nNew development: A nearby bell tolls, shifting the mood. "
                "Press the scene forward with a specific intent like `talk`, `investigate`, or `move`."
            )
        return message, repeat_count
