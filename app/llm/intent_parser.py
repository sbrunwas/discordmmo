from __future__ import annotations

import logging

from app.models.intents import Intent

log = logging.getLogger(__name__)


KEYWORDS = {
    "look": "LOOK",
    "move": "MOVE",
    "go": "MOVE",
    "investigate": "INVESTIGATE",
    "rest short": "REST_SHORT",
    "rest long": "REST_LONG",
}


def parse_intent(text: str) -> Intent:
    lower = text.strip().lower()
    action = "UNKNOWN"
    target = None
    if lower == "!help":
        action = "HELP"
    elif lower == "!start":
        action = "START"
    else:
        for k, v in KEYWORDS.items():
            if lower.startswith(k):
                action = v
                parts = lower.split(maxsplit=1)
                target = parts[1] if len(parts) > 1 else None
                break
    intent = Intent(action=action, target=target, raw_text=text)
    log.info("parsed_intent %s", intent.model_dump_json())
    return intent
