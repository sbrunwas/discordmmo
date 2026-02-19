from __future__ import annotations

import random

from app.npcforge.schemas import CandidateAction, NPCOutput, NPCSheet, NPCState, Observation

ALLOWED_TICK_KINDS = {
    "move",
    "rumor",
    "seek_help",
    "speak_to_other_npc",
    "change_availability",
    "offer_reconciliation_hook",
}


def _alignment_bias(sheet: NPCSheet) -> dict[str, int]:
    law_chaos = 0
    moral = 0
    if sheet.alignment.startswith("lawful"):
        law_chaos = 2
    elif sheet.alignment.startswith("chaotic"):
        law_chaos = -2
    if sheet.alignment.endswith("good"):
        moral = 2
    elif sheet.alignment.endswith("evil"):
        moral = -2
    return {"law_chaos": law_chaos, "moral": moral}


def plan_npc_tick(
    sheet: NPCSheet,
    state: NPCState,
    observation: Observation,
    *,
    rng: random.Random | None = None,
) -> NPCOutput:
    picker = rng or random.Random(0)
    bias = _alignment_bias(sheet)
    actions: list[CandidateAction] = []

    move_chance = 0.15 + (0.2 if bias["law_chaos"] < 0 else -0.08)
    if picker.random() < max(0.02, min(0.45, move_chance)):
        target = picker.choice(sheet.allowed_locations or [observation.location_id])
        if target != observation.location_id:
            actions.append(
                CandidateAction(
                    kind="move",
                    target=target,
                    content=f"Relocate to {target} to pursue current goals.",
                )
            )

    if bias["moral"] >= 1:
        actions.append(CandidateAction(kind="seek_help", content="Check if anyone nearby needs assistance."))
    elif bias["moral"] <= -1:
        actions.append(CandidateAction(kind="rumor", content="Spread a self-serving version of recent events."))
    else:
        actions.append(CandidateAction(kind="speak_to_other_npc", content="Exchange practical updates with another local."))

    if state.availability == "open" and picker.random() < 0.2:
        actions.append(
            CandidateAction(
                kind="change_availability",
                content="Take a brief break before returning.",
                metadata={"availability": "busy", "duration_minutes": 15},
            )
        )

    filtered = [action for action in actions if action.kind in ALLOWED_TICK_KINDS]
    new_goal = state.current_goal
    if filtered:
        new_goal = f"Follow through on: {filtered[0].kind}."
    return NPCOutput(
        dialogue="",
        intent="npc_tick",
        candidate_actions=filtered[:3],
        state_updates={"current_goal": new_goal},
        memory_update=None,
    )
