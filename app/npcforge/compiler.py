from __future__ import annotations

from dataclasses import dataclass

from app.npcforge.schemas import CandidateAction, NPCSheet


@dataclass
class CompiledAction:
    mode: str  # executable|flavor
    action_type: str
    payload: dict


def compile_candidate_action(
    action: CandidateAction,
    *,
    sheet: NPCSheet,
    current_location_id: str,
    allowed_locations: set[str],
    key_npc: bool,
) -> CompiledAction:
    if action.kind == "move":
        target = (action.target or "").strip()
        if target and target in allowed_locations:
            if key_npc and target not in set(sheet.allowed_locations):
                return CompiledAction(
                    mode="flavor",
                    action_type="FLAVOR_ONLY",
                    payload={"reason": "key_npc_move_blocked", "candidate": action.model_dump()},
                )
            if target == current_location_id:
                return CompiledAction(mode="flavor", action_type="FLAVOR_ONLY", payload={"reason": "already_there"})
            return CompiledAction(
                mode="executable",
                action_type="MOVE_NPC",
                payload={"target_location_id": target, "reason": action.content or "npc_relocation"},
            )
        return CompiledAction(mode="flavor", action_type="FLAVOR_ONLY", payload={"reason": "invalid_move_target"})

    if action.kind == "change_availability":
        availability = str(action.metadata.get("availability", "busy"))
        return CompiledAction(
            mode="executable",
            action_type="CHANGE_AVAILABILITY",
            payload={
                "availability": availability if availability in {"open", "busy", "away"} else "busy",
                "duration_minutes": int(action.metadata.get("duration_minutes", 15)),
            },
        )

    if action.kind in {"refuse_service", "offer_reconciliation_hook", "speak", "rumor", "offer", "help", "seek_help", "speak_to_other_npc"}:
        return CompiledAction(
            mode="flavor",
            action_type="FLAVOR_ONLY",
            payload={"candidate": action.model_dump()},
        )

    return CompiledAction(mode="flavor", action_type="FLAVOR_ONLY", payload={"reason": "unsupported_kind"})


def compile_candidate_actions(
    actions: list[CandidateAction],
    *,
    sheet: NPCSheet,
    current_location_id: str,
    allowed_locations: set[str],
    key_npc: bool,
) -> list[CompiledAction]:
    return [
        compile_candidate_action(
            action,
            sheet=sheet,
            current_location_id=current_location_id,
            allowed_locations=allowed_locations,
            key_npc=key_npc,
        )
        for action in actions
    ]
