from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Intent(BaseModel):
    action: Literal["LOOK", "MOVE", "INVESTIGATE", "TALK", "REST_SHORT", "REST_LONG", "HELP", "START", "UNKNOWN"]
    target: str | None = None
    confidence: float = 1.0
    clarify_question: str | None = None
    raw_text: str = Field(min_length=1)
