from __future__ import annotations

import json
import logging
import random
import re
import time

from app.db.store import Store
from app.engine.arc_engine import initialize_arc
from app.engine.combat_engine import trigger_combat
from app.engine.rules_engine import death_save_roll
from app.llm.intent_parser import parse_intent
from app.llm.narrator import narrate_outcome
from app.models.core import ActionResult, EngineOutcome
from app.npcforge.compiler import compile_candidate_actions
from app.npcforge.generator import generate_npc_sheet, initial_state_for_sheet
from app.npcforge.memory import apply_output_state_updates, decay_mood
from app.npcforge.planner import plan_npc_tick
from app.npcforge.policy import produce_npc_output
from app.npcforge.schemas import NPCSheet, NPCState, Observation

log = logging.getLogger(__name__)


class WorldEngine:
    WORLD_SEED_VERSION = 2

    def __init__(self, store: Store, narrator_client, rng_seed: int = 1337) -> None:
        self.store = store
        self.narrator_client = narrator_client
        self.rng = random.Random(rng_seed)

    def initialize_world(self) -> None:
        seeded = self.store.get_arc_value("WORLD_SEED_VERSION")
        if seeded and seeded.get("version") == self.WORLD_SEED_VERSION:
            return
        self._seed_locations()
        initialize_arc(self.store)
        self._seed_npcs()
        self.store.set_arc_value("WORLD_SEED_VERSION", {"version": self.WORLD_SEED_VERSION})
        self.store.set_arc_value("NPCFORGE_LAST_GLOBAL_TICK_TS", {"ts": int(time.time())})
        self.store.write_event("system", "WORLD_INITIALIZED", {"locations": 2})

    def handle_message(self, actor_id: str, actor_name: str, text: str) -> ActionResult:
        log.info("discord_message_received actor=%s text=%s", actor_id, text)
        session = self.store.get_session_state(actor_id)
        mode_before = session["mode"]
        player = self.store.get_player(actor_id)
        early_intent = parse_intent(text, llm_client=None, user_id=actor_id, context=None)
        if early_intent.action == "HELP":
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
        if early_intent.action == "START":
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
        self._maybe_run_npc_planner_tick()

        # Keep conversational continuity deterministic and avoid burning intent-LLM calls on every follow-up turn.
        npc_target = self._active_dialogue_npc_target(actor_id, player["location_id"])
        if npc_target is not None and self._looks_like_dialogue_continuation(text):
            talk = self._handle_talk(actor_id, text, player["location_id"], npc_target)
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="dialogue",
                action="TALK",
                message=self._talk_response_message(talk["outcome"], player["location_id"]),
                player=player,
                thread_id=talk["thread_id"],
                active_npc_id=talk["npc_id"],
            )

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

        encounter_row = self.store.get_latest_encounter(actor_id, player["location_id"])
        if encounter_row is not None:
            combat = self._handle_active_combat(actor_id, player["location_id"], intent, encounter_row)
            return self._narrate_and_respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after=combat["mode_after"],
                action=intent.action,
                outcome=combat["outcome"],
                player=player,
                thread_id=combat["thread_id"],
                hint_type=combat["hint_type"],
                active_npc_id=None,
                active_encounter_id=combat["active_encounter_id"],
            )

        if npc_target is not None and self._should_continue_dialogue(text, intent.action):
            talk = self._handle_talk(actor_id, text, player["location_id"], npc_target)
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="dialogue",
                action="TALK",
                message=self._talk_response_message(talk["outcome"], player["location_id"]),
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
            outcome = EngineOutcome(
                action="LOOK",
                result="looked",
                roll=None,
                hp_delta=0,
                xp_delta=0,
                location_id=player["location_id"],
                npc_name=None,
                npc_reply=None,
                is_scene_description=True,
            )
            return self._narrate_and_respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="explore",
                action="LOOK",
                outcome=outcome,
                player=player,
                thread_id=session.get("active_thread_id"),
                hint_type="explore",
                active_npc_id=None,
            )
        if intent.action == "MOVE":
            target = self._resolve_move_target(intent.target)
            was_visited = self.store.has_visited_location(actor_id, target)
            self.store.move_player(actor_id, target)
            self.store.write_event(actor_id, "PLAYER_MOVED", {"to": target})
            if not was_visited:
                self.store.mark_location_visited(actor_id, target)
            player = self.store.get_player(actor_id)
            outcome = EngineOutcome(
                action="MOVE",
                result="moved",
                roll=None,
                hp_delta=0,
                xp_delta=0,
                location_id=target,
                npc_name=None,
                npc_reply=None,
                is_scene_description=not was_visited,
            )
            return self._narrate_and_respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="explore",
                action="MOVE",
                outcome=outcome,
                player=player,
                thread_id=f"travel:{target}",
                hint_type="explore",
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
                message=self._talk_response_message(talk["outcome"], player["location_id"]),
                player=player,
                thread_id=talk["thread_id"],
                active_npc_id=talk["npc_id"],
            )
        if intent.action == "STATS":
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="explore",
                action="STATS",
                message=f"HP: {player['hp']} | XP: {player['xp']} | Injury: {player['injury']}\n{self._exploration_prompt(player['location_id'])}",
                player=player,
                thread_id="sheet:stats",
            )
        if intent.action == "INVENTORY":
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="explore",
                action="INVENTORY",
                message="Inventory is not fully implemented yet. You currently carry basic field gear and a travel satchel.",
                player=player,
                thread_id="sheet:inventory",
            )
        if intent.action == "SKILLS":
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="explore",
                action="SKILLS",
                message="Skills are in prototype. Core approach options are: look, investigate, talk, move, and rest.",
                player=player,
                thread_id="sheet:skills",
            )
        if intent.action == "RESPEC":
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="explore",
                action="RESPEC",
                message="Respec is not available yet. Planned: redistribute skill points once the skill system is live.",
                player=player,
                thread_id="sheet:respec",
            )
        if intent.action == "FACTIONS":
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="explore",
                action="FACTIONS",
                message="Factions are emerging in Asterfall. No allegiance chosen yet.",
                player=player,
                thread_id="faction:overview",
            )
        if intent.action == "RECAP":
            recap_events = self.store.get_recent_events(actor_id, limit=5)
            recap = ", ".join(event["event_type"] for event in recap_events) if recap_events else "No major events yet."
            relationship_events = sum(1 for event in recap_events if event["event_type"] == "NPC_STATE_UPDATED")
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="explore",
                action="RECAP",
                message=f"Recent timeline: {recap}. Relationships changed: {relationship_events}.",
                player=player,
                thread_id="recap:recent",
            )
        if intent.action == "DUEL":
            return self._respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="explore",
                action="DUEL",
                message="Duel mode is not implemented yet. Use `investigate` if you want to provoke a local combat encounter.",
                player=player,
                thread_id="combat:duel",
            )
        if intent.action == "INVESTIGATE":
            roll = death_save_roll(self.rng)
            payload = {"roll": roll, "discovery": "constellation sigil" if roll >= 10 else "old mortar dust"}
            self.store.write_event(actor_id, "INVESTIGATED", payload)
            xp_delta = 0
            if roll >= 10:
                self.store.update_player_progress(actor_id, xp_delta=1)
                xp_delta = 1
            if roll >= 15:
                encounter = trigger_combat(self.store, actor_id, player["location_id"])
                outcome = EngineOutcome(
                    action="INVESTIGATE",
                    result="combat_started",
                    roll=roll,
                    hp_delta=0,
                    xp_delta=xp_delta,
                    location_id=player["location_id"],
                    npc_name=None,
                    npc_reply=None,
                    is_scene_description=False,
                )
                return self._narrate_and_respond(
                    actor_id,
                    session=session,
                    mode_before=mode_before,
                    mode_after="combat",
                    action="INVESTIGATE",
                    outcome=outcome,
                    player=player,
                    thread_id=f"combat:{encounter}",
                    hint_type="combat",
                    active_npc_id=None,
                    active_encounter_id=encounter,
                )
            discovery_thread = "mystery:constellation_sigil" if payload["discovery"] == "constellation sigil" else "mystery:ruin_dust"
            outcome = EngineOutcome(
                action="INVESTIGATE",
                result="discovery_sigil" if payload["discovery"] == "constellation sigil" else "discovery_dust",
                roll=roll,
                hp_delta=0,
                xp_delta=xp_delta,
                location_id=player["location_id"],
                npc_name=None,
                npc_reply=None,
                is_scene_description=False,
            )
            return self._narrate_and_respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="explore",
                action="INVESTIGATE",
                outcome=outcome,
                player=player,
                thread_id=discovery_thread,
                hint_type="explore",
                active_npc_id=None,
            )
        if intent.action in {"REST_SHORT", "REST_LONG"}:
            self.store.write_event(actor_id, intent.action, {})
            outcome = EngineOutcome(
                action=intent.action,
                result="rested",
                roll=None,
                hp_delta=0,
                xp_delta=0,
                location_id=player["location_id"],
                npc_name=None,
                npc_reply=None,
                is_scene_description=False,
            )
            return self._narrate_and_respond(
                actor_id,
                session=session,
                mode_before=mode_before,
                mode_after="explore",
                action=intent.action,
                outcome=outcome,
                player=player,
                thread_id=session.get("active_thread_id"),
                hint_type="explore",
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
            "known_actions": [
                "LOOK",
                "MOVE",
                "INVESTIGATE",
                "TALK",
                "REST_SHORT",
                "REST_LONG",
                "HELP",
                "START",
                "STATS",
                "INVENTORY",
                "SKILLS",
                "RESPEC",
                "FACTIONS",
                "RECAP",
                "DUEL",
            ],
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

    def _handle_active_combat(self, actor_id: str, location_id: str, intent, encounter_row) -> dict[str, object]:
        state = json.loads(encounter_row["state_json"])
        encounter_id = encounter_row["encounter_id"]
        enemy_role = state.get("enemy_role", "threat")
        turn = int(state.get("turn", 1))
        player = self.store.get_player(actor_id)
        bonus = 0
        if player is not None:
            bonus = int(player["xp"] // 10) - int(player["injury"])

        if intent.action in {"LOOK", "UNKNOWN"}:
            return {
                "outcome": EngineOutcome(
                    action=intent.action,
                    result="combat_status",
                    roll=None,
                    hp_delta=0,
                    xp_delta=0,
                    location_id=location_id,
                    npc_name=None,
                    npc_reply=None,
                    is_scene_description=False,
                ),
                "mode_after": "combat",
                "thread_id": f"combat:{encounter_id}",
                "active_encounter_id": encounter_id,
                "hint_type": "combat",
            }

        if intent.action == "MOVE":
            self.store.delete_actor_encounters(actor_id, location_id)
            self.store.write_event(actor_id, "COMBAT_DISENGAGED", {"encounter_id": encounter_id, "location_id": location_id})
            return {
                "outcome": EngineOutcome(
                    action="MOVE",
                    result="disengaged",
                    roll=None,
                    hp_delta=0,
                    xp_delta=0,
                    location_id=location_id,
                    npc_name=None,
                    npc_reply=None,
                    is_scene_description=False,
                ),
                "mode_after": "explore",
                "thread_id": f"travel:{location_id}",
                "active_encounter_id": None,
                "hint_type": "explore",
            }

        if intent.action == "INVESTIGATE":
            roll = death_save_roll(self.rng)
            total = roll + bonus
            if total >= 10:
                self.store.delete_actor_encounters(actor_id, location_id)
                self.store.update_player_progress(actor_id, xp_delta=3)
                self.store.write_event(
                    actor_id,
                    "COMBAT_RESOLVED",
                    {"encounter_id": encounter_id, "location_id": location_id, "roll": roll, "bonus": bonus, "result": "won"},
                )
                return {
                    "outcome": EngineOutcome(
                        action="INVESTIGATE",
                        result="combat_won",
                        roll=roll,
                        hp_delta=0,
                        xp_delta=3,
                        location_id=location_id,
                        npc_name=None,
                        npc_reply=None,
                        is_scene_description=False,
                    ),
                    "mode_after": "explore",
                    "thread_id": f"travel:{location_id}",
                    "active_encounter_id": None,
                    "hint_type": "explore",
                }

            state["turn"] = turn + 1
            self.store.update_encounter_state(encounter_id, state)
            self.store.update_player_progress(actor_id, hp_delta=-2, injury_delta=1)
            self.store.write_event(
                actor_id,
                "COMBAT_PROGRESS",
                {"encounter_id": encounter_id, "location_id": location_id, "roll": roll, "bonus": bonus, "turn": state["turn"]},
            )
            player_after = self.store.get_player(actor_id)
            hp = player_after["hp"] if player_after is not None else "?"
            if isinstance(hp, int) and hp <= 0:
                self.store.delete_actor_encounters(actor_id, location_id)
                return {
                    "outcome": EngineOutcome(
                        action="INVESTIGATE",
                        result="combat_lost",
                        roll=roll,
                        hp_delta=-2,
                        xp_delta=0,
                        location_id=location_id,
                        npc_name=None,
                        npc_reply=None,
                        is_scene_description=False,
                    ),
                    "mode_after": "explore",
                    "thread_id": f"travel:{location_id}",
                    "active_encounter_id": None,
                    "hint_type": "explore",
                }
            return {
                "outcome": EngineOutcome(
                    action="INVESTIGATE",
                    result="combat_hit",
                    roll=roll,
                    hp_delta=-2,
                    xp_delta=0,
                    location_id=location_id,
                    npc_name=None,
                    npc_reply=None,
                    is_scene_description=False,
                ),
                "mode_after": "combat",
                "thread_id": f"combat:{encounter_id}",
                "active_encounter_id": encounter_id,
                "hint_type": "combat",
            }

        return {
            "outcome": EngineOutcome(
                action=intent.action,
                result="combat_status",
                roll=None,
                hp_delta=0,
                xp_delta=0,
                location_id=location_id,
                npc_name=None,
                npc_reply=None,
                is_scene_description=False,
            ),
            "mode_after": "combat",
            "thread_id": f"combat:{encounter_id}",
            "active_encounter_id": encounter_id,
            "hint_type": "combat",
        }

    def _exploration_prompt(self, location_id: str = "town_square") -> str:
        npcs = self.store.list_npcs_at_location(location_id)
        talk_options = ", ".join(f"`talk {row['name'].lower()}`" for row in npcs[:3]) if npcs else "`talk`"
        exits = ", ".join(f"`move {row['location_id']}`" for row in self.store.list_locations() if row["location_id"] != location_id)
        if not exits:
            exits = "`move town_square`"
        return f"Try: `look`, `investigate`, {talk_options}, {exits}, `rest short`, or `!help`."

    def _combat_prompt(self) -> str:
        return "Try: `investigate` to engage carefully, `move` to disengage, or `look` for status."

    def _resolve_move_target(self, target: str | None) -> str:
        locations = self.store.list_locations()
        if not locations:
            return "town_square"
        if not target:
            return "town_square"
        lower = target.lower().strip()
        if "ruin" in lower:
            return "ruin_upper"
        if "town" in lower or "square" in lower:
            return "town_square"
        for row in locations:
            if lower == row["location_id"].lower() or lower in row["name"].lower():
                return row["location_id"]
        for row in locations:
            token_hits = [token for token in row["name"].lower().split() if token in lower]
            if token_hits:
                return row["location_id"]
        return "town_square"

    def _seed_npcs(self) -> None:
        self._seed_npc(
            "quartermaster_brann",
            "Quartermaster Brann",
            "town_square",
            "Gruff ex-mercenary quartermaster. Practical, blunt, unexpectedly kind to new adventurers. "
            "Always references supply shortages, local rumors, and tactical caution.",
            is_key=True,
        )
        self._seed_npc(
            "scholar_ione",
            "Scholar Ione",
            "town_square",
            "Curious ruin scholar obsessed with celestial inscriptions. Speaks quickly, asks follow-up questions, "
            "and connects current events to ancient lore.",
            is_key=True,
        )
        self._seed_npc(
            "traveler_sera",
            "Traveler Sera",
            "town_square",
            "Friendly roadworn scout who shares rumors, campfire stories, and practical travel advice. "
            "Warm and conversational, but wary about dangerous ruins.",
        )
        self._seed_npc(
            "warden_lyra",
            "Warden Lyra",
            "ruin_upper",
            "Calm ruin warden with a guarded tone. Protective of the chamber and sensitive to magical disturbances. "
            "Encourages discipline and careful observation.",
            is_key=True,
        )

    def _seed_locations(self) -> None:
        if self.store.get_location("town_square") is None:
            self.store.upsert_location(
                "town_square",
                "Asterfall Commons",
                "A warm tavern square built atop a half-exposed celestial ruin.",
            )
        if self.store.get_location("ruin_upper") is None:
            self.store.upsert_location(
                "ruin_upper",
                "Upper Chamber",
                "Dusty star-metal plates hum beneath the stone.",
            )

    def _seed_npc(self, npc_id: str, name: str, location_id: str, persona: str, is_key: bool = False) -> None:
        if self.store.get_npc(npc_id) is None:
            self.store.upsert_npc(npc_id, name, location_id, is_key=is_key)
        if self.store.get_npc_profile(npc_id) is None:
            self.store.upsert_npc_profile(npc_id, persona)
        npc = self.store.get_npc(npc_id)
        if npc is None:
            return
        persona_json = self.store.get_npc_persona_json(npc_id)
        memory_json = self.store.get_npc_memory_json(npc_id)
        if not persona_json:
            tier = 3 if is_key else 1
            sheet = generate_npc_sheet(npc_id, name, location_id, tier=tier, llm_client=self.narrator_client)
            persona_json = sheet.model_dump()
            self.store.update_npc_persona(npc_id, persona_json)
        if not memory_json:
            try:
                sheet = NPCSheet(**persona_json)
            except Exception:
                sheet = generate_npc_sheet(npc_id, name, location_id, tier=3 if is_key else 1, llm_client=None)
                self.store.update_npc_persona(npc_id, sheet.model_dump())
            self.store.update_npc_memory(npc_id, initial_state_for_sheet(sheet).model_dump())

    def _handle_talk(self, actor_id: str, player_text: str, location_id: str, target: str | None) -> dict[str, object]:
        npcs = self.store.list_npcs_at_location(location_id)
        if not npcs:
            return {
                "outcome": EngineOutcome(
                    action="TALK",
                    result="talk_no_npc",
                    roll=None,
                    hp_delta=0,
                    xp_delta=0,
                    location_id=location_id,
                    npc_name=None,
                    npc_reply=None,
                    is_scene_description=False,
                ),
                "npc_id": "",
                "thread_id": "thread:none",
            }

        npc = self._select_npc(npcs, target)
        if npc is None:
            available = ", ".join(row["name"] for row in npcs)
            return {
                "outcome": EngineOutcome(
                    action="TALK",
                    result="talk_ambiguous",
                    roll=None,
                    hp_delta=0,
                    xp_delta=0,
                    location_id=location_id,
                    npc_name=None,
                    npc_reply=f"I couldn't tell who you meant. Try one of: {available}.",
                    is_scene_description=False,
                ),
                "npc_id": "",
                "thread_id": "thread:none",
            }

        location = self.store.get_location(location_id)
        history = self.store.get_npc_dialogue_history(npc["npc_id"], actor_id, limit=8)
        thread_id = f"npc:{npc['npc_id']}"
        sheet, state = self._npc_sheet_state(npc)
        obs = Observation(
            now_ts=int(time.time()),
            player_id=actor_id,
            player_utterance=player_text,
            location_id=location_id,
            location_name=location["name"] if location else "Unknown",
            world_summary=f"Recent events: {', '.join(event['event_type'] for event in self.store.get_recent_events(actor_id, limit=4))}",
            recent_events=[event["event_type"] for event in self.store.get_recent_events(actor_id, limit=6)],
            visible_context={
                "npc_name": npc["name"],
                "location_description": location["description"] if location else "",
                "history_tail": history[-4:],
            },
        )
        output = produce_npc_output(sheet, state, obs, llm_client=self.narrator_client)
        updated_state = apply_output_state_updates(decay_mood(state, steps=1), output)
        self.store.update_npc_memory(npc["npc_id"], updated_state.model_dump())
        reply = output.dialogue or f"{npc['name']} studies you carefully but offers no clear reply."
        self.store.append_npc_dialogue(npc["npc_id"], actor_id, "player", player_text)
        self.store.append_npc_dialogue(npc["npc_id"], actor_id, "npc", reply)
        self.store.upsert_npc_dialogue_summary(npc["npc_id"], actor_id, updated_state.memory_summary)
        if len(history) >= 8:
            self.store.trim_npc_dialogue_history(npc["npc_id"], actor_id, keep_last=4)
        self.store.write_event(
            actor_id,
            "NPC_SPOKE",
            {
                "npc_id": npc["npc_id"],
                "location_id": location_id,
                "dialogue": reply[:300],
                "tags": ["npc_greeting", "npc_memory"],
            },
        )
        if output.memory_update is not None:
            self.store.write_event(
                actor_id,
                "NPC_STATE_UPDATED",
                {
                    "npc_id": npc["npc_id"],
                    "location_id": location_id,
                    "delta_affinity": output.memory_update.delta_affinity,
                    "delta_trust": output.memory_update.delta_trust,
                    "delta_respect": output.memory_update.delta_respect,
                    "tags": ["npc_memory", "npc_relationship"],
                },
            )
        compiled = compile_candidate_actions(
            output.candidate_actions,
            sheet=sheet,
            current_location_id=location_id,
            allowed_locations={row["location_id"] for row in self.store.list_locations()},
            key_npc=bool(npc["is_key"]),
        )
        self._apply_compiled_npc_actions(
            actor_id=actor_id,
            npc=npc,
            sheet=sheet,
            state=updated_state,
            compiled_actions=compiled,
            source="talk",
            now_ts=obs.now_ts,
        )
        self.store.upsert_thread(
            actor_id,
            thread_id,
            "npc_dialogue",
            f"Conversation with {npc['name']}",
            reply,
            status="ACTIVE",
        )
        return {
            "outcome": EngineOutcome(
                action="TALK",
                result="talk_replied",
                roll=None,
                hp_delta=0,
                xp_delta=0,
                location_id=location_id,
                npc_name=npc["name"],
                npc_reply=reply,
                is_scene_description=False,
            ),
            "npc_id": npc["npc_id"],
            "thread_id": thread_id,
        }

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
            if event["event_type"] not in {"NPC_DIALOGUE", "NPC_SPOKE"}:
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

    def _npc_sheet_state(self, npc) -> tuple[NPCSheet, NPCState]:
        npc_id = str(npc["npc_id"])
        name = str(npc["name"])
        location_id = str(npc["location_id"])
        is_key = bool(npc["is_key"])
        persona_json = self.store.get_npc_persona_json(npc_id)
        memory_json = self.store.get_npc_memory_json(npc_id)
        if not persona_json:
            sheet = generate_npc_sheet(npc_id, name, location_id, tier=3 if is_key else 1, llm_client=self.narrator_client)
            self.store.update_npc_persona(npc_id, sheet.model_dump())
        else:
            try:
                sheet = NPCSheet(**persona_json)
            except Exception:
                sheet = generate_npc_sheet(npc_id, name, location_id, tier=3 if is_key else 1, llm_client=None)
                self.store.update_npc_persona(npc_id, sheet.model_dump())
        if not memory_json:
            state = initial_state_for_sheet(sheet)
            self.store.update_npc_memory(npc_id, state.model_dump())
        else:
            try:
                state = NPCState(**memory_json)
            except Exception:
                state = initial_state_for_sheet(sheet)
                self.store.update_npc_memory(npc_id, state.model_dump())
        return sheet, state

    def _consume_npc_move_budget(self, now_ts: int, max_moves_per_hour: int = 6) -> bool:
        hour_bucket = time.strftime("%Y%m%d%H", time.gmtime(now_ts))
        key = f"NPCFORGE_MOVE_BUDGET_{hour_bucket}"
        current = self.store.get_arc_value(key) or {"count": 0}
        count = int(current.get("count", 0))
        if count >= max_moves_per_hour:
            return False
        self.store.set_arc_value(key, {"count": count + 1})
        return True

    def _apply_compiled_npc_actions(
        self,
        *,
        actor_id: str,
        npc,
        sheet: NPCSheet,
        state: NPCState,
        compiled_actions,
        source: str,
        now_ts: int,
    ) -> None:
        npc_id = str(npc["npc_id"])
        for compiled in compiled_actions:
            if compiled.mode == "executable" and compiled.action_type == "MOVE_NPC":
                if not self._consume_npc_move_budget(now_ts):
                    self.store.write_event(
                        actor_id,
                        "FLAVOR_ONLY",
                        {
                            "npc_id": npc_id,
                            "reason": "npc_move_hourly_limit",
                            "tags": ["npc_tick"] if source == "tick" else [],
                        },
                    )
                    continue
                target = str(compiled.payload["target_location_id"])
                self.store.move_npc(npc_id, target)
                self.store.write_event(
                    actor_id,
                    "NPC_MOVED",
                    {
                        "npc_id": npc_id,
                        "from": str(npc["location_id"]),
                        "to": target,
                        "reason": compiled.payload.get("reason", "npc_move"),
                        "tags": ["npc_tick"] if source == "tick" else [],
                    },
                )
            elif compiled.mode == "executable" and compiled.action_type == "CHANGE_AVAILABILITY":
                availability = str(compiled.payload.get("availability", "busy"))
                duration_minutes = int(compiled.payload.get("duration_minutes", 15))
                updated_state = state.model_copy(deep=True)
                updated_state.availability = availability if availability in {"open", "busy", "away"} else "busy"
                updated_state.unavailable_until_ts = now_ts + (duration_minutes * 60)
                self.store.update_npc_memory(npc_id, updated_state.model_dump())
                self.store.write_event(
                    actor_id,
                    "NPC_STATE_UPDATED",
                    {
                        "npc_id": npc_id,
                        "availability": updated_state.availability,
                        "unavailable_until_ts": updated_state.unavailable_until_ts,
                        "tags": ["npc_tick"] if source == "tick" else ["npc_relationship"],
                    },
                )
            else:
                self.store.write_event(
                    actor_id,
                    "FLAVOR_ONLY",
                    {
                        "npc_id": npc_id,
                        "compiled_action": compiled.action_type,
                        "payload": compiled.payload,
                        "tags": ["npc_tick"] if source == "tick" else [],
                    },
                )

    def run_npc_planner_tick(self, now_ts: int | None = None, max_npcs: int = 2) -> int:
        ts = int(now_ts or time.time())
        all_npcs = self.store.list_npcs()
        acted = 0
        for npc in all_npcs[: max(1, max_npcs)]:
            npc_last_tick = int(npc["npc_last_tick_ts"] or 0)
            if npc_last_tick and ts - npc_last_tick < 300:
                continue
            sheet, state = self._npc_sheet_state(npc)
            location = self.store.get_location(npc["location_id"])
            observation = Observation(
                now_ts=ts,
                player_id=None,
                player_utterance=None,
                location_id=str(npc["location_id"]),
                location_name=location["name"] if location is not None else str(npc["location_id"]),
                world_summary="Autonomous NPC planner tick. Arc progression is disallowed.",
                recent_events=[event["event_type"] for event in self.store.get_recent_events("system", limit=4)],
                visible_context={"source": "npc_tick"},
            )
            decayed_state = decay_mood(state, steps=1)
            output = plan_npc_tick(sheet, decayed_state, observation, rng=self.rng)
            updated_state = apply_output_state_updates(decayed_state, output)
            self.store.update_npc_memory(str(npc["npc_id"]), updated_state.model_dump())
            compiled = compile_candidate_actions(
                output.candidate_actions,
                sheet=sheet,
                current_location_id=str(npc["location_id"]),
                allowed_locations={row["location_id"] for row in self.store.list_locations()},
                key_npc=bool(npc["is_key"]),
            )
            self._apply_compiled_npc_actions(
                actor_id="system",
                npc=npc,
                sheet=sheet,
                state=updated_state,
                compiled_actions=compiled,
                source="tick",
                now_ts=ts,
            )
            self.store.update_npc_last_tick_ts(str(npc["npc_id"]), ts)
            self.store.write_event(
                "system",
                "NPC_TICK",
                {"npc_id": str(npc["npc_id"]), "intent": output.intent, "tags": ["npc_tick"]},
            )
            acted += 1
        self.store.set_arc_value("NPCFORGE_LAST_GLOBAL_TICK_TS", {"ts": ts})
        return acted

    def _maybe_run_npc_planner_tick(self) -> None:
        now_ts = int(time.time())
        marker = self.store.get_arc_value("NPCFORGE_LAST_GLOBAL_TICK_TS") or {"ts": now_ts}
        last_ts = int(marker.get("ts", now_ts))
        if now_ts - last_ts < 300:
            return
        self.run_npc_planner_tick(now_ts=now_ts, max_npcs=1)

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

    def _looks_like_dialogue_continuation(self, text: str) -> bool:
        lower = text.strip().lower()
        if not lower:
            return False
        if lower.startswith("!"):
            return False
        blocked_prefixes = (
            "move",
            "go ",
            "rest",
            "investigate",
            "talk ",
            "look",
            "help",
            "stats",
            "inventory",
            "skills",
            "respec",
            "factions",
            "recap",
            "duel",
            "start",
        )
        return not any(lower.startswith(prefix) for prefix in blocked_prefixes)

    def _talk_response_message(self, outcome: EngineOutcome, location_id: str) -> str:
        if not outcome.npc_reply:
            return f"No one answers clearly.\n\n{self._exploration_prompt(location_id)}"
        return f"{outcome.npc_reply}\n\n{self._exploration_prompt(location_id)}"

    def _build_npc_summary(
        self,
        previous: str,
        history: list[dict[str, str]],
        player_text: str,
        npc_reply: str,
        actor_id: str,
        npc_name: str,
    ) -> str:
        if len(history) >= 8:
            prompt = (
                f"Summarize this dialogue between a player and {npc_name} in 3-5 concise bullet-like sentences. "
                "Keep concrete facts, unresolved questions, and the current conversational thread."
                f"\nPrevious summary: {previous}\n"
                f"Recent turns: {history}\n"
                f"Latest turn player: {player_text}\n"
                f"Latest turn npc: {npc_reply}"
            )
            data = self.narrator_client.complete_json(prompt, user_id=actor_id, temperature=0)
            text = str(data.get("text", "")).strip()
            if text:
                return text[:600]
        base = previous.strip()
        addition = f" Player asked: {player_text.strip()} NPC replied: {npc_reply.strip()}"
        merged = (base + addition).strip()
        return merged[:600]

    def _narrate_and_respond(
        self,
        actor_id: str,
        *,
        session: dict,
        mode_before: str,
        mode_after: str,
        action: str,
        outcome: EngineOutcome,
        player,
        thread_id: str | None,
        hint_type: str,
        ok: bool = True,
        active_npc_id: str | None = None,
        active_encounter_id: str | None = None,
    ) -> ActionResult:
        location_id = outcome.location_id or (player["location_id"] if player is not None else "town_square")
        location = self.store.get_location(location_id)
        scene_memory = self.store.get_scene_memory(actor_id)
        last_narration = str(scene_memory.get("last_narration", ""))
        last_npc_exchange = ""
        if outcome.npc_name:
            last_npc_exchange = f"{outcome.npc_name}: {outcome.npc_reply or ''}"
        narration = narrate_outcome(
            self.narrator_client,
            outcome=outcome,
            location_name=location["name"] if location is not None else "Unknown",
            location_description=location["description"] if location is not None else "",
            recent_events=self.store.get_recent_events(actor_id, limit=4),
            last_npc_exchange=last_npc_exchange,
            last_narration=last_narration,
            session_state=session,
            user_id=actor_id,
        )
        hint = self._combat_prompt() if hint_type == "combat" else self._exploration_prompt(location_id)
        final_message = f"{narration}\n\n{hint}"

        updated_scene = self.store.get_scene_memory(actor_id)
        updated_scene["last_narration"] = narration
        self.store.upsert_scene_memory(actor_id, updated_scene)

        return self._respond(
            actor_id,
            session=session,
            mode_before=mode_before,
            mode_after=mode_after,
            action=action,
            message=final_message,
            player=player,
            thread_id=thread_id,
            ok=ok,
            active_npc_id=active_npc_id,
            active_encounter_id=active_encounter_id,
        )

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
        snapshot = self._scene_memory_snapshot(mode_after, action, player, thread_id, final_message)
        existing_scene = self.store.get_scene_memory(actor_id)
        existing_scene.update(snapshot)
        self.store.upsert_scene_memory(actor_id, existing_scene)
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
