from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.npcforge.schemas import NPCSheet, NPCState

TEMPLATES_PATH = Path(__file__).resolve().parent / "templates" / "npc_sheets.json"


def _load_templates() -> list[dict[str, Any]]:
    raw = TEMPLATES_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    return data if isinstance(data, list) else []


def _template_for_npc(npc_id: str, templates: list[dict[str, Any]]) -> dict[str, Any]:
    if not templates:
        raise ValueError("npc_templates_missing")
    idx = abs(hash(npc_id)) % len(templates)
    return templates[idx]


def generate_npc_sheet(
    npc_id: str,
    name: str,
    location_id: str,
    *,
    tier: int = 1,
    llm_client=None,
) -> NPCSheet:
    templates = _load_templates()
    template = _template_for_npc(npc_id, templates)
    allowed_locations = ["town_square", "ruin_upper"] if tier >= 3 else ["town_square", "ruin_upper"]
    # LLM-assisted generation is optional and safely falls back to template output.
    if llm_client is not None:
        try:
            prompt = (
                "Create a strict JSON NPC sheet with keys alignment, background_paragraphs, ideals, bonds, flaws, "
                "motivation, fear, archetype, skills, voice_style for a fantasy settlement character.\n"
                f"NPC id: {npc_id}\n"
                f"Name: {name}\n"
                f"Current location: {location_id}\n"
                "Return only JSON."
            )
            data = llm_client.complete_json(prompt, user_id="system")
            text = str(data.get("text", "")).strip()
            parsed = json.loads(text) if text.startswith("{") else None
            if isinstance(parsed, dict):
                merged = dict(template)
                merged.update(parsed)
                template = merged
        except Exception:
            pass
    return NPCSheet(
        npc_id=npc_id,
        name=name,
        alignment=str(template["alignment"]),
        background_paragraphs=[str(x) for x in template["background_paragraphs"][:4]],
        ideals=[str(x) for x in template["ideals"][:4]],
        bonds=[str(x) for x in template["bonds"][:4]],
        flaws=[str(x) for x in template["flaws"][:4]],
        motivation=str(template["motivation"]),
        fear=str(template["fear"]),
        archetype=str(template["archetype"]),
        skills=[str(x) for x in template["skills"][:8]],
        voice_style=str(template["voice_style"]),
        baseline_mood=0,
        allowed_locations=allowed_locations,
        tier=tier,
    )


def initial_state_for_sheet(sheet: NPCSheet) -> NPCState:
    return NPCState(
        mood=sheet.baseline_mood,
        baseline_mood=sheet.baseline_mood,
        current_goal=f"Advance day-to-day goals as a {sheet.archetype.lower()}.",
    )
