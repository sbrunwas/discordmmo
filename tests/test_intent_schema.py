import pytest
from pydantic import ValidationError

from app.llm.intent_parser import parse_intent
from app.models.intents import Intent


def test_intent_schema_valid():
    intent = Intent(action="LOOK", raw_text="look around")
    assert intent.action == "LOOK"


def test_intent_schema_invalid_action():
    with pytest.raises(ValidationError):
        Intent(action="BREAK", raw_text="nope")


def test_parse_intent_natural_language():
    assert parse_intent("I look around the square").action == "LOOK"
    assert parse_intent("can I investigate this wall?").action == "INVESTIGATE"
    move_intent = parse_intent("we should head to the ruin")
    assert move_intent.action == "MOVE"
    assert move_intent.target == "ruin"


def test_parse_intent_command_variant():
    intent = parse_intent("!rest long please")
    assert intent.action == "REST_LONG"
