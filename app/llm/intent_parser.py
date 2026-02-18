from __future__ import annotations

import logging
import re

from app.models.intents import Intent

log = logging.getLogger(__name__)


COMMAND_MAP = {
    "!help": "HELP",
    "!start": "START",
    "!look": "LOOK",
    "!investigate": "INVESTIGATE",
    "!move": "MOVE",
    "!go": "MOVE",
    "!rest short": "REST_SHORT",
    "!rest long": "REST_LONG",
}

LOOK_WORDS = ("look", "observe", "scan")
INVESTIGATE_WORDS = ("investigate", "inspect", "examine", "search")
MOVE_WORDS = ("move", "go", "walk", "travel", "head")


def parse_intent(text: str) -> Intent:
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
        elif any(re.search(rf"\b{word}\b", lower) for word in LOOK_WORDS):
            action = "LOOK"
        elif any(re.search(rf"\b{word}\b", lower) for word in MOVE_WORDS):
            action = "MOVE"

    if action == "MOVE":
        if "ruin" in lower:
            target = "ruin"
        elif "town" in lower or "square" in lower:
            target = "town"

    intent = Intent(action=action, target=target, raw_text=text)
    log.info("parsed_intent %s", intent.model_dump_json())
    return intent
