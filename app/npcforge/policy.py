from __future__ import annotations

import time
from typing import Any

from app.npcforge.schemas import CandidateAction, NPCOutput, NPCSheet, NPCState, Observation, OutcomeFeedback


def _player_metric(values: dict[str, int], player_id: str) -> int:
    return int(values.get(player_id, 0))


def _greeting(sheet: NPCSheet, state: NPCState, obs: Observation, player_id: str) -> str:
    stage = int(state.greeting_stage_by_player.get(player_id, 0))
    trust = _player_metric(state.trust_by_player, player_id)
    affinity = _player_metric(state.affinity_by_player, player_id)
    grudges = set(state.grudge_flags_by_player.get(player_id, []))
    last_ts = int(state.last_interaction_ts_by_player.get(player_id, 0))
    long_absence = last_ts > 0 and (obs.now_ts - last_ts) > 7 * 24 * 3600

    if stage == 0:
        return f"{sheet.name} sizes you up before offering a formal nod."
    if long_absence:
        return "It's been a while, and they make that clear with a measured pause."
    if grudges or trust < 20:
        return f"{sheet.name}'s tone is curt, and old friction sits between you."
    if trust >= 65 and affinity >= 40:
        return f"{sheet.name} greets you warmly, already connecting today to your past efforts."
    return f"{sheet.name} greets you with familiar restraint."


def _relationship_reply(sheet: NPCSheet, state: NPCState, obs: Observation, player_id: str) -> tuple[str, list[CandidateAction]]:
    utterance = (obs.player_utterance or "").strip()
    lower = utterance.lower()
    trust = _player_metric(state.trust_by_player, player_id)
    respect = _player_metric(state.respect_by_player, player_id)
    affinity = _player_metric(state.affinity_by_player, player_id)
    grudges = set(state.grudge_flags_by_player.get(player_id, []))
    bonds = set(state.bond_flags_by_player.get(player_id, []))
    candidates: list[CandidateAction] = []

    if grudges or trust < 20:
        candidates.append(
            CandidateAction(
                kind="refuse_service",
                content="I don't trust this exchange yet.",
                metadata={"reason": "grudge_or_low_trust"},
            )
        )
        candidates.append(
            CandidateAction(
                kind="offer_reconciliation_hook",
                content="Bring proof you can be relied on: deliver a sealed letter to the watch post.",
                metadata={"hook_type": "repair"},
            )
        )
        return "Not today. Earn back some trust, then we can speak plainly.", candidates

    if "help" in lower or "can you" in lower:
        candidates.append(
            CandidateAction(
                kind="help",
                content="Offer practical assistance that fits the NPC role.",
                metadata={"topic": "requested_help"},
            )
        )

    if "rumor" in lower or "heard" in lower or "news" in lower:
        candidates.append(CandidateAction(kind="rumor", content="Share one rumor that may or may not be complete."))

    if trust >= 60 and ("saved_me" in bonds or affinity >= 45):
        return "For you, I'll be direct: the safer route is through the market arches, not the open lane.", candidates
    if respect >= 60:
        return "You ask like someone who plans ahead. I'll give you the short version and the risk behind it.", candidates
    return "I'll answer what I can, but keep your expectations practical.", candidates


def _llm_dialogue(sheet: NPCSheet, state: NPCState, obs: Observation, llm_client) -> str:
    if llm_client is None:
        return ""
    prompt = (
        "You are an NPC in a grounded fantasy MMO. Reply in-character in 1-3 sentences without game mechanics.\n"
        f"Name: {sheet.name}\n"
        f"Voice: {sheet.voice_style}\n"
        f"Alignment: {sheet.alignment}\n"
        f"Motivation: {sheet.motivation}\n"
        f"Fear: {sheet.fear}\n"
        f"Current goal: {state.current_goal}\n"
        f"Memory summary: {state.memory_summary}\n"
        f"Player said: {obs.player_utterance or ''}\n"
        "Respond only with the NPC dialogue."
    )
    data = llm_client.complete_json(prompt, user_id=obs.player_id or "system", temperature=0.7)
    text = str(data.get("text", "")).strip()
    if text and not text.startswith("[stub]"):
        return text
    return ""


def produce_npc_output(
    sheet: NPCSheet,
    state: NPCState,
    observation: Observation,
    *,
    llm_client=None,
) -> NPCOutput:
    player_id = observation.player_id or "system"
    greeting = _greeting(sheet, state, observation, player_id)
    relation_dialogue, candidates = _relationship_reply(sheet, state, observation, player_id)
    llm_text = _llm_dialogue(sheet, state, observation, llm_client=llm_client)
    dialogue = llm_text or f"{greeting} {relation_dialogue}"

    feedback = OutcomeFeedback(
        what_happened=f"Spoke with {player_id} in {observation.location_name}.",
        emotional_reaction="Guarded optimism" if candidates and candidates[0].kind != "refuse_service" else "Caution",
        success=True,
        delta_affinity=2 if "help" in (observation.player_utterance or "").lower() else 1,
        delta_trust=2 if "thank" in (observation.player_utterance or "").lower() else 1,
        delta_respect=1,
        ts=observation.now_ts,
    )

    updates: dict[str, Any] = {
        "mood": max(-100, min(100, state.mood + (1 if "thank" in (observation.player_utterance or "").lower() else 0))),
        "greeting_stage_by_player": {player_id: min(3, int(state.greeting_stage_by_player.get(player_id, 0)) + 1)},
        "last_interaction_ts_by_player": {player_id: observation.now_ts},
    }
    return NPCOutput(
        dialogue=dialogue[:500],
        intent="maintain_relationship",
        candidate_actions=candidates,
        state_updates=updates,
        memory_update=feedback,
    )


def default_observation_for_tick(location_id: str, location_name: str) -> Observation:
    return Observation(
        now_ts=int(time.time()),
        player_id=None,
        player_utterance=None,
        location_id=location_id,
        location_name=location_name,
        world_summary="Routine world pulse; no arc advancement allowed.",
        recent_events=[],
        visible_context={},
    )
