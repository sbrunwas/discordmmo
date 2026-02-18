from __future__ import annotations

from app.llm.client import LLMClient
from app.llm.schemas import NarrationRequest, NarrationResponse


def narrate(client: LLMClient, scene: str, action: str) -> str:
    req = NarrationRequest(scene=scene, action=action)
    data = client.complete_json(req.model_dump_json())
    return NarrationResponse(text=data["text"]).text
