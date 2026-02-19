from __future__ import annotations

from app.npcforge.schemas import NPCOutput, NPCState, OutcomeFeedback


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def decay_mood(state: NPCState, steps: int = 1) -> NPCState:
    mood = int(state.mood)
    baseline = int(state.baseline_mood)
    for _ in range(max(0, steps)):
        if mood > baseline:
            mood -= 1
        elif mood < baseline:
            mood += 1
    updated = state.model_copy(deep=True)
    updated.mood = _clamp(mood, -100, 100)
    return updated


def _merge_player_map(base: dict[str, int], updates: dict[str, int], minimum: int, maximum: int) -> dict[str, int]:
    merged = dict(base)
    for player_id, delta in updates.items():
        merged[player_id] = _clamp(merged.get(player_id, 0) + int(delta), minimum, maximum)
    return merged


def _merge_player_stage(base: dict[str, int], updates: dict[str, int]) -> dict[str, int]:
    merged = dict(base)
    for player_id, value in updates.items():
        merged[player_id] = _clamp(int(value), 0, 3)
    return merged


def _merge_flags(base: dict[str, list[str]], player_id: str, new_flags: list[str]) -> dict[str, list[str]]:
    merged = dict(base)
    existing = list(merged.get(player_id, []))
    for flag in new_flags:
        if flag not in existing:
            existing.append(flag)
    merged[player_id] = existing[:10]
    return merged


def _append_memory_summary(summary: str, line: str) -> str:
    text = f"{summary.strip()} {line.strip()}".strip()
    return text[:600]


def apply_feedback(state: NPCState, player_id: str, feedback: OutcomeFeedback) -> NPCState:
    updated = state.model_copy(deep=True)
    updated.affinity_by_player = _merge_player_map(updated.affinity_by_player, {player_id: feedback.delta_affinity}, -100, 100)
    updated.trust_by_player = _merge_player_map(updated.trust_by_player, {player_id: feedback.delta_trust}, 0, 100)
    updated.respect_by_player = _merge_player_map(updated.respect_by_player, {player_id: feedback.delta_respect}, 0, 100)
    updated.bond_flags_by_player = _merge_flags(updated.bond_flags_by_player, player_id, feedback.new_bond_flags)
    updated.grudge_flags_by_player = _merge_flags(updated.grudge_flags_by_player, player_id, feedback.new_grudge_flags)
    updated.last_interaction_ts_by_player[player_id] = int(feedback.ts)
    updated.memory_summary = _append_memory_summary(
        updated.memory_summary,
        f"{feedback.what_happened} Reaction: {feedback.emotional_reaction}.",
    )
    if feedback.what_happened:
        pinned = [p for p in updated.pinned_memories if p]
        if feedback.what_happened not in pinned:
            pinned.append(feedback.what_happened[:120])
        updated.pinned_memories = pinned[-10:]
    return updated


def apply_output_state_updates(state: NPCState, output: NPCOutput) -> NPCState:
    updated = state.model_copy(deep=True)
    updates = output.state_updates
    if "mood" in updates:
        updated.mood = _clamp(int(updates["mood"]), -100, 100)
    if "current_goal" in updates:
        updated.current_goal = str(updates["current_goal"])[:220]
    if "memory_summary" in updates:
        updated.memory_summary = str(updates["memory_summary"])[:600]
    if "greeting_stage_by_player" in updates and isinstance(updates["greeting_stage_by_player"], dict):
        updated.greeting_stage_by_player = _merge_player_stage(
            updated.greeting_stage_by_player,
            {str(k): int(v) for k, v in updates["greeting_stage_by_player"].items()},
        )
    if "last_interaction_ts_by_player" in updates and isinstance(updates["last_interaction_ts_by_player"], dict):
        for player_id, ts in updates["last_interaction_ts_by_player"].items():
            updated.last_interaction_ts_by_player[str(player_id)] = int(ts)
    if output.memory_update is not None:
        player_id = next(iter(updates.get("last_interaction_ts_by_player", {"system": output.memory_update.ts})), "system")
        updated = apply_feedback(updated, player_id, output.memory_update)
    return updated
