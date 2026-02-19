from __future__ import annotations

from app.llm.npc_dialogue import generate_npc_reply


class FakeClient:
    def __init__(self, text: str) -> None:
        self.text = text

    def complete_json(self, prompt: str, user_id: str = "system", **kwargs) -> dict:
        return {"text": self.text}


def test_npc_dialogue_extracts_message_from_jsonish_output():
    client = FakeClient('{"npc_persona":"lorekeeper","message":"The ruins hum at dusk because the sigils wake."}')
    reply = generate_npc_reply(
        client,
        user_id="p1",
        npc_name="Scholar Ione",
        npc_persona="Scholar persona",
        location_name="Asterfall Commons",
        location_description="Ruins below the square.",
        player_message="What causes that resonance?",
        history=[],
        summary="",
        active_thread="npc:scholar_ione",
    )
    assert reply == "The ruins hum at dusk because the sigils wake."
