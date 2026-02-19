from __future__ import annotations

from app.npcforge.memory import apply_feedback, apply_output_state_updates, decay_mood
from app.npcforge.schemas import NPCOutput, NPCState, OutcomeFeedback


def test_mood_decay_moves_toward_baseline():
    state = NPCState(mood=10, baseline_mood=7)
    decayed = decay_mood(state, steps=2)
    assert decayed.mood == 8


def test_feedback_deltas_are_clamped_and_memory_is_bounded():
    state = NPCState(
        affinity_by_player={"p1": 95},
        trust_by_player={"p1": 98},
        respect_by_player={"p1": 97},
        memory_summary="x" * 590,
    )
    feedback = OutcomeFeedback(
        what_happened="A meaningful conversation happened.",
        emotional_reaction="Hopeful",
        delta_affinity=15,
        delta_trust=15,
        delta_respect=15,
        ts=5,
    )
    updated = apply_feedback(state, "p1", feedback)
    assert updated.affinity_by_player["p1"] == 100
    assert updated.trust_by_player["p1"] == 100
    assert updated.respect_by_player["p1"] == 100
    assert len(updated.memory_summary) <= 600


def test_apply_output_updates_greeting_stage_bounds():
    state = NPCState(greeting_stage_by_player={"p1": 3})
    output = NPCOutput(
        dialogue="hi",
        intent="test",
        state_updates={"greeting_stage_by_player": {"p1": 8}, "mood": 999},
    )
    updated = apply_output_state_updates(state, output)
    assert updated.greeting_stage_by_player["p1"] == 3
    assert updated.mood == 100
