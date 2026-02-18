from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Intent(BaseModel):
    action: Literal["LOOK", "MOVE", "INVESTIGATE", "REST_SHORT", "REST_LONG", "HELP", "START", "UNKNOWN"]
    target: str | None = None
    raw_text: str = Field(min_length=1)
