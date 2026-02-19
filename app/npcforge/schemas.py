from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Alignment = Literal[
    "lawful_good",
    "neutral_good",
    "chaotic_good",
    "lawful_neutral",
    "true_neutral",
    "chaotic_neutral",
    "lawful_evil",
    "neutral_evil",
    "chaotic_evil",
]

ActionKind = Literal[
    "speak",
    "move",
    "rumor",
    "refuse_service",
    "offer",
    "help",
    "change_availability",
    "offer_reconciliation_hook",
    "seek_help",
    "speak_to_other_npc",
]


class CandidateAction(BaseModel):
    kind: ActionKind
    target: str | None = None
    content: str | None = None
    intensity: int = Field(default=1, ge=1, le=5)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NPCSheet(BaseModel):
    npc_id: str
    name: str
    alignment: Alignment
    background_paragraphs: list[str] = Field(min_length=2, max_length=4)
    ideals: list[str] = Field(min_length=1, max_length=4)
    bonds: list[str] = Field(min_length=1, max_length=4)
    flaws: list[str] = Field(min_length=1, max_length=4)
    motivation: str
    fear: str
    archetype: str
    skills: list[str] = Field(min_length=2, max_length=8)
    voice_style: str
    baseline_mood: int = Field(default=0, ge=-100, le=100)
    allowed_locations: list[str] = Field(default_factory=list)
    tier: int = Field(default=1, ge=1, le=3)


class NPCState(BaseModel):
    mood: int = Field(default=0, ge=-100, le=100)
    baseline_mood: int = Field(default=0, ge=-100, le=100)
    affinity_by_player: dict[str, int] = Field(default_factory=dict)
    trust_by_player: dict[str, int] = Field(default_factory=dict)
    respect_by_player: dict[str, int] = Field(default_factory=dict)
    bond_flags_by_player: dict[str, list[str]] = Field(default_factory=dict)
    grudge_flags_by_player: dict[str, list[str]] = Field(default_factory=dict)
    last_interaction_ts_by_player: dict[str, int] = Field(default_factory=dict)
    greeting_stage_by_player: dict[str, int] = Field(default_factory=dict)
    current_goal: str = "Maintain routine and gather local information."
    memory_summary: str = Field(default="", max_length=600)
    pinned_memories: list[str] = Field(default_factory=list, max_length=10)
    availability: Literal["open", "busy", "away"] = "open"
    unavailable_until_ts: int | None = None


class Observation(BaseModel):
    now_ts: int
    player_id: str | None = None
    player_utterance: str | None = None
    location_id: str
    location_name: str
    world_summary: str = ""
    recent_events: list[str] = Field(default_factory=list)
    visible_context: dict[str, Any] = Field(default_factory=dict)


class OutcomeFeedback(BaseModel):
    what_happened: str
    emotional_reaction: str
    success: bool = True
    delta_affinity: int = Field(default=0, ge=-30, le=30)
    delta_trust: int = Field(default=0, ge=-30, le=30)
    delta_respect: int = Field(default=0, ge=-30, le=30)
    new_bond_flags: list[str] = Field(default_factory=list)
    new_grudge_flags: list[str] = Field(default_factory=list)
    ts: int


class NPCOutput(BaseModel):
    dialogue: str
    intent: str
    candidate_actions: list[CandidateAction] = Field(default_factory=list)
    state_updates: dict[str, Any] = Field(default_factory=dict)
    memory_update: OutcomeFeedback | None = None
