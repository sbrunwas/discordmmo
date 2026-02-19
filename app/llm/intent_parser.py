from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.llm.client import LLMClient
from app.models.intents import Intent

log = logging.getLogger(__name__)


COMMAND_MAP = {
    "!help": "HELP",
    "!start": "START",
    "!look": "LOOK",
    "!investigate": "INVESTIGATE",
    "!move": "MOVE",
    "!go": "MOVE",
    "!talk": "TALK",
    "!rest short": "REST_SHORT",
    "!rest long": "REST_LONG",
}

LOOK_WORDS = ("look", "observe", "scan")
INVESTIGATE_WORDS = ("investigate", "inspect", "examine", "search")
MOVE_WORDS = ("move", "go", "walk", "travel", "head")
SOCIAL_WORDS = ("talk", "speak", "ask", "approach", "greet", "chat")


def parse_intent(
    text: str,
    llm_client: LLMClient | None = None,
    user_id: str = "system",
    context: dict[str, Any] | None = None,
) -> Intent:
    parsed = _parse_intent_rules(text)
    if parsed.action != "UNKNOWN":
        return parsed
    if llm_client is not None:
        llm_intent = _parse_intent_with_llm(llm_client, text, user_id=user_id, context=context)
        if llm_intent is not None:
            return llm_intent
    return parsed


def _parse_intent_with_llm(
    llm_client: LLMClient,
    text: str,
    user_id: str,
    context: dict[str, Any] | None = None,
) -> Intent | None:
    system_prompt = (
        "You convert player text into a strict game intent JSON object. "
        "Return only valid JSON with keys action, target, confidence, clarify_question. "
        "action must be one of LOOK,MOVE,INVESTIGATE,TALK,REST_SHORT,REST_LONG,HELP,START,UNKNOWN. "
        "target must be string or null. confidence must be number 0..1. "
        "clarify_question must be string or null. "
        "Map social interactions (talk/speak/approach/ask) to TALK, not LOOK."
    )
    try:
        user_payload = {
            "player_message": text,
            "context": context or {},
        }
        data = llm_client.complete_json(
            json.dumps(user_payload, sort_keys=True),
            user_id=user_id,
            system_prompt=system_prompt,
            response_format={"type": "json_object"},
            temperature=0,
        )
        if data.get("error") == "openrouter_404":
            return Intent(
                action="UNKNOWN",
                target=None,
                confidence=0.0,
                clarify_question=str(data.get("clarify_question")),
                raw_text=text,
            )
        if data.get("error") == "budget_exhausted":
            return Intent(
                action="UNKNOWN",
                target=None,
                confidence=0.0,
                clarify_question="LLM budget exhausted for today; using basic parser.",
                raw_text=text,
            )
        intent = Intent(
            action=str(data["action"]).upper(),
            target=data.get("target"),
            confidence=float(data.get("confidence", 0.75)),
            clarify_question=data.get("clarify_question"),
            raw_text=text,
        )
        log.info("parsed_intent_llm %s", intent.model_dump_json())
        return intent
    except Exception:
        log.warning("intent_llm_parse_failed_fallback_unknown", exc_info=True)
        return Intent(
            action="UNKNOWN",
            target=None,
            confidence=0.1,
            clarify_question="I could not parse that. Try rephrasing your action.",
            raw_text=text,
        )


def _parse_intent_rules(text: str) -> Intent:
    lower = text.strip().lower()
    action = "UNKNOWN"
    target = None

    for command, mapped_action in COMMAND_MAP.items():
        if lower == command or lower.startswith(f"{command} "):
            action = mapped_action
            parts = lower.split(maxsplit=1)
            target = parts[1] if len(parts) > 1 else None
            break

    if action == "UNKNOWN":
        if re.search(r"\brest\b", lower):
            if re.search(r"\blong\b", lower):
                action = "REST_LONG"
            elif re.search(r"\bshort\b", lower):
                action = "REST_SHORT"

    if action == "UNKNOWN":
        if any(re.search(rf"\b{word}\b", lower) for word in INVESTIGATE_WORDS):
            action = "INVESTIGATE"
        elif any(re.search(rf"\b{word}\b", lower) for word in SOCIAL_WORDS):
            action = "TALK"
        elif any(re.search(rf"\b{word}\b", lower) for word in LOOK_WORDS):
            action = "LOOK"
        elif any(re.search(rf"\b{word}\b", lower) for word in MOVE_WORDS):
            action = "MOVE"

    if action == "TALK":
        if " to " in lower:
            target = lower.split(" to ", 1)[1].strip()
        elif " with " in lower:
            target = lower.split(" with ", 1)[1].strip()
        if target:
            target = target[:64]
        if "traveler" in lower or "travellers" in lower:
            target = "travelers"
        elif "scholar" in lower or "scholars" in lower:
            target = "scholar"
        elif "merchant" in lower:
            target = "merchant"
    elif action == "INVESTIGATE":
        if "traveler" in lower or "travellers" in lower:
            target = "travelers"
        elif "fire pit" in lower:
            target = "fire_pit"
        elif "merchant" in lower:
            target = "merchant"

    if action == "MOVE":
        if "ruin" in lower:
            target = "ruin"
        elif "town" in lower or "square" in lower:
            target = "town"

    intent = Intent(action=action, target=target, raw_text=text)
    log.info("parsed_intent %s", intent.model_dump_json())
    return intent
