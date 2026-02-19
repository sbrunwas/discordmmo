from __future__ import annotations

import json
import re
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
    summary: str,
    active_thread: str,
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
        "conversation_summary": summary,
        "active_thread": active_thread,
        "conversation_history": history[-10:],
        "player_message": player_message,
    }
    data = client.complete_json(
        json.dumps(payload, sort_keys=True),
        user_id=user_id,
        system_prompt=system_prompt,
        temperature=0.7,
    )
    text = _extract_dialogue_text(str(data.get("text", "")).strip())
    if text:
        return text
    return f"{npc_name} studies you carefully but offers no clear reply."


def _extract_dialogue_text(raw: str) -> str:
    if not raw:
        return ""
    text = raw.strip()
    parsed = _try_parse_jsonish(text)
    if isinstance(parsed, dict):
        for key in ("message", "reply", "dialogue", "text"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return text


def _try_parse_jsonish(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None
