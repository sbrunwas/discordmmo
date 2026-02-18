from __future__ import annotations

from pydantic import BaseModel


class NarrationRequest(BaseModel):
    scene: str
    action: str


class NarrationResponse(BaseModel):
    text: str
