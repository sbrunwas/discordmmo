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

def parse_intent(
    text: str,
    llm_client: LLMClient | None = None,
    user_id: str = "system",
    context: dict[str, Any] | None = None,
) -> Intent:
    parsed = _parse_intent_explicit(text)
    if parsed is not None:
        return parsed
    if llm_client is not None:
        llm_intent = _parse_intent_with_llm(llm_client, text, user_id=user_id, context=context)
        if llm_intent is not None:
            return llm_intent
    return Intent(
        action="UNKNOWN",
        target=None,
        confidence=0.1,
        clarify_question="I could not parse that. Try `!help` for commands.",
        raw_text=text,
    )


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


def _parse_intent_explicit(text: str) -> Intent | None:
    lower = text.strip().lower()
    if not lower:
        return Intent(action="UNKNOWN", target=None, raw_text=text)

    for command, mapped_action in COMMAND_MAP.items():
        if lower == command or lower.startswith(f"{command} "):
            target = None
            parts = lower.split(maxsplit=1)
            if len(parts) > 1:
                target = parts[1]
            intent = Intent(action=mapped_action, target=target, raw_text=text)
            log.info("parsed_intent_explicit %s", intent.model_dump_json())
            return intent

    # Imperative command style without "!"
    match = re.match(r"^(help|start|look|investigate|move|go|talk|rest)\b(?:\s+(.*))?$", lower)
    if not match:
        return None

    verb = match.group(1)
    remainder = (match.group(2) or "").strip()
    if verb == "help":
        action = "HELP"
    elif verb == "start":
        action = "START"
    elif verb == "look":
        action = "LOOK"
    elif verb == "investigate":
        action = "INVESTIGATE"
    elif verb in {"move", "go"}:
        action = "MOVE"
    elif verb == "talk":
        action = "TALK"
    elif verb == "rest":
        if remainder.startswith("long"):
            action = "REST_LONG"
        elif remainder.startswith("short"):
            action = "REST_SHORT"
        else:
            return None
    else:
        return None

    target = remainder if remainder else None
    intent = Intent(action=action, target=target, raw_text=text)
    log.info("parsed_intent_explicit %s", intent.model_dump_json())
    return intent
