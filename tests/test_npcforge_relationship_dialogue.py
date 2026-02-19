from __future__ import annotations

from app.npcforge.policy import produce_npc_output
from app.npcforge.schemas import NPCSheet, NPCState, Observation


def _sheet() -> NPCSheet:
    return NPCSheet(
        npc_id="scholar_ione",
        name="Scholar Ione",
        alignment="neutral_good",
        background_paragraphs=["p1", "p2"],
        ideals=["Truth"],
        bonds=["The archive"],
        flaws=["Obsessive"],
        motivation="Decode ruins.",
        fear="Losing primary evidence.",
        archetype="Scholar",
        skills=["lore", "conversation"],
        voice_style="Quick and precise.",
        tier=3,
        allowed_locations=["town_square", "ruin_upper"],
    )


def test_high_trust_dialogue_references_prior_help():
    state = NPCState(
        trust_by_player={"p1": 80},
        affinity_by_player={"p1": 70},
        bond_flags_by_player={"p1": ["saved_me"]},
        greeting_stage_by_player={"p1": 2},
        last_interaction_ts_by_player={"p1": 100},
    )
    obs = Observation(
        now_ts=150,
        player_id="p1",
        player_utterance="Can you help me with this route?",
        location_id="town_square",
        location_name="Asterfall Commons",
    )
    output = produce_npc_output(_sheet(), state, obs, llm_client=None)
    assert "direct" in output.dialogue.lower() or "warml" in output.dialogue.lower()


def test_grudge_dialogue_refuses_and_offers_repair_hook():
    state = NPCState(
        trust_by_player={"p1": 10},
        grudge_flags_by_player={"p1": ["insulted_me"]},
        greeting_stage_by_player={"p1": 1},
    )
    obs = Observation(
        now_ts=150,
        player_id="p1",
        player_utterance="Tell me everything about the sigil.",
        location_id="town_square",
        location_name="Asterfall Commons",
    )
    output = produce_npc_output(_sheet(), state, obs, llm_client=None)
    kinds = [action.kind for action in output.candidate_actions]
    assert "refuse_service" in kinds
    assert "offer_reconciliation_hook" in kinds
