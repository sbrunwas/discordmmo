from __future__ import annotations

import json
from typing import Any

from app.llm.client import LLMClient
from app.models.core import EngineOutcome


def narrate_outcome(
    client,
    *,
    outcome: EngineOutcome,
    location_name: str,
    location_description: str,
    recent_events: list[dict],
    last_npc_exchange: str,
    last_narration: str,
    session_state: dict,
    user_id: str,
) -> str:
    system_prompt = (
        "You are writing narrative output for a Discord MMO.\n"
        "Write 2-4 sentences of immersive second-person prose about what just happened.\n"
        "Never use mechanical language such as roll values, HP, XP, bonuses, encounter IDs, or UUIDs.\n"
        "If hp_delta is negative, describe injury through sensation and atmosphere, not numbers.\n"
        "If xp_delta is positive, suggest subtle growth (confidence, clarity, momentum).\n"
        "If is_scene_description is true, emphasize what the player perceives in the location.\n"
        "If npc_reply exists, weave that speech naturally into narration, do not prefix with labels.\n"
        "Do not repeat last_narration; vary sentence structure, focus, and mood.\n"
        "Ground continuity in recent_events and session_state mode."
    )
    payload: dict[str, Any] = {
        "outcome": {
            "action": outcome.action,
            "result": outcome.result,
            "roll": outcome.roll,
            "hp_delta": outcome.hp_delta,
            "xp_delta": outcome.xp_delta,
            "location_id": outcome.location_id,
            "npc_name": outcome.npc_name,
            "npc_reply": outcome.npc_reply,
            "is_scene_description": outcome.is_scene_description,
        },
        "location_name": location_name,
        "location_description": location_description,
        "recent_events": recent_events[-4:],
        "last_npc_exchange": last_npc_exchange,
        "last_narration": last_narration,
        "session_state": {"mode": session_state.get("mode")},
    }
    data = client.complete_json(
        json.dumps(payload, sort_keys=True),
        user_id=user_id,
        system_prompt=system_prompt,
        temperature=0.6,
    )
    text = str(data.get("text", "")).strip()
    if text and not text.startswith("[stub]"):
        return text
    return _fallback_narration(outcome, location_name, location_description)


def _fallback_narration(outcome: EngineOutcome, location_name: str, location_description: str) -> str:
    if outcome.npc_reply:
        return f"In {location_name}, {outcome.npc_name} answers in a low, steady voice: \"{outcome.npc_reply}\""
    if outcome.result == "combat_won":
        return "You steady your breathing as the threat falls away, the square slowly regaining its rhythm."
    if outcome.result == "combat_hit":
        return "Pain flares as the clash turns against you, and the world narrows to breath, grit, and motion."
    if outcome.result == "combat_started":
        return "A sudden shift in the crowd's mood warns you too late; danger steps out from the noise around you."
    if outcome.result == "discovery_sigil":
        return "A hidden pattern resolves beneath your gaze, and the ruin yields a clue it had long concealed."
    if outcome.result == "discovery_dust":
        return "Your search turns up only faint traces of old stone and timeworn mortar."
    if outcome.result == "moved":
        if outcome.is_scene_description:
            return f"You arrive at {location_name}, taking in the place with fresh attention: {location_description}"
        return f"You make your way to {location_name}, the path familiar underfoot."
    if outcome.result == "rested":
        return "You let the noise of the square fade and gather yourself before moving again."
    return "The moment shifts subtly around you, and the story presses on."
