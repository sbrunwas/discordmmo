from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Proposal(BaseModel):
    proposal_type: Literal["SIDE_QUEST", "ATTITUDE_SHIFT", "DIALOGUE_UNLOCK", "FACTION_SENTIMENT", "RUMOR"]
    content: str
    actor_id: str
