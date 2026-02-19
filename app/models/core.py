from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ActionResult:
    ok: bool
    message: str


@dataclass
class EngineOutcome:
    action: str
    result: str
    roll: int | None
    hp_delta: int
    xp_delta: int
    location_id: str | None
    npc_name: str | None
    npc_reply: str | None
    is_scene_description: bool
