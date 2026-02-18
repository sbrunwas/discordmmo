import pytest
from pydantic import ValidationError

from app.models.intents import Intent


def test_intent_schema_valid():
    intent = Intent(action="LOOK", raw_text="look around")
    assert intent.action == "LOOK"


def test_intent_schema_invalid_action():
    with pytest.raises(ValidationError):
        Intent(action="BREAK", raw_text="nope")
