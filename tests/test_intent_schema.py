import pytest
from pydantic import ValidationError

from app.llm.intent_parser import parse_intent
from app.models.intents import Intent


class FakeLLMClient:
    def __init__(self, response: dict):
        self._response = response
        self.last_prompt = ""
        self.last_user_id = ""

    def complete_json(self, prompt: str, user_id: str = "system", **kwargs) -> dict:
        self.last_prompt = prompt
        self.last_user_id = user_id
        return self._response


def test_intent_schema_valid():
    intent = Intent(action="LOOK", raw_text="look around")
    assert intent.action == "LOOK"


def test_intent_schema_invalid_action():
    with pytest.raises(ValidationError):
        Intent(action="BREAK", raw_text="nope")


def test_parse_intent_natural_language():
    assert parse_intent("look around the square").action == "LOOK"
    assert parse_intent("investigate wall").action == "INVESTIGATE"
    talk_intent = parse_intent("talk scholar ione")
    assert talk_intent.action == "TALK"
    assert talk_intent.target == "scholar ione"
    move_intent = parse_intent("move ruin")
    assert move_intent.action == "MOVE"
    assert move_intent.target == "ruin"


def test_parse_intent_command_variant():
    intent = parse_intent("!rest long please")
    assert intent.action == "REST_LONG"
    assert parse_intent("!factions").action == "FACTIONS"
    assert parse_intent("!recap arc").action == "RECAP"


def test_parse_intent_uses_llm_when_rules_return_unknown():
    intent = parse_intent(
        "what can you do",
        llm_client=FakeLLMClient({"action": "HELP", "target": None}),
    )
    assert intent.action == "HELP"


def test_parse_intent_falls_back_when_llm_output_is_invalid():
    intent = parse_intent(
        "what can you do",
        llm_client=FakeLLMClient({"text": "oops"}),
    )
    assert intent.action == "UNKNOWN"
    assert intent.target is None
    assert intent.clarify_question is not None


def test_parse_intent_without_llm_returns_unknown_for_ambiguous_text():
    intent = parse_intent("I would like to speak with the scholar")
    assert intent.action == "UNKNOWN"


def test_parse_intent_includes_context_in_llm_payload():
    client = FakeLLMClient({"action": "LOOK", "target": None})
    parse_intent(
        "what do I see",
        llm_client=client,
        user_id="u1",
        context={"location": {"name": "Asterfall Commons"}, "recent_events": ["PLAYER_STARTED"]},
    )
    assert "\"player_message\": \"what do I see\"" in client.last_prompt
    assert "\"location\"" in client.last_prompt
    assert client.last_user_id == "u1"
