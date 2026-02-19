from __future__ import annotations

import json
from typing import Any

from app.llm.client import LLMClient


def generate_npc_reply(
    client: LLMClient,
    *,
    user_id: str,
    npc_name: str,
    npc_persona: str,
    location_name: str,
    location_description: str,
    player_message: str,
    history: list[dict[str, str]],
) -> str:
    system_prompt = (
        "You are roleplaying an NPC in a Discord MMO. "
        "Stay in-character. Keep responses to 1-4 sentences. "
        "Be specific and reactive to player intent. "
        "Do not narrate as a game master; speak as the NPC directly."
    )
    payload: dict[str, Any] = {
        "npc_name": npc_name,
        "npc_persona": npc_persona,
        "location_name": location_name,
        "location_description": location_description,
        "conversation_history": history[-10:],
        "player_message": player_message,
    }
    data = client.complete_json(
        json.dumps(payload, sort_keys=True),
        user_id=user_id,
        system_prompt=system_prompt,
        temperature=0.7,
    )
    text = str(data.get("text", "")).strip()
    if text:
        return text
    return f"{npc_name} studies you carefully but offers no clear reply."
