from __future__ import annotations

from pydantic import BaseModel


class EventRecord(BaseModel):
    actor_id: str
    event_type: str
    payload_json: str
