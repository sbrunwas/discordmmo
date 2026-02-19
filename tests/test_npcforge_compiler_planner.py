from __future__ import annotations

import random

from app.npcforge.compiler import compile_candidate_action
from app.npcforge.generator import generate_npc_sheet, initial_state_for_sheet
from app.npcforge.planner import ALLOWED_TICK_KINDS, plan_npc_tick
from app.npcforge.schemas import CandidateAction, Observation


def test_compiler_maps_move_to_executable_and_unknown_to_flavor():
    sheet = generate_npc_sheet("n1", "Test NPC", "town_square", tier=1, llm_client=None)
    move = compile_candidate_action(
        CandidateAction(kind="move", target="ruin_upper"),
        sheet=sheet,
        current_location_id="town_square",
        allowed_locations={"town_square", "ruin_upper"},
        key_npc=False,
    )
    refuse = compile_candidate_action(
        CandidateAction(kind="refuse_service", content="No."),
        sheet=sheet,
        current_location_id="town_square",
        allowed_locations={"town_square", "ruin_upper"},
        key_npc=False,
    )
    assert move.mode == "executable"
    assert move.action_type == "MOVE_NPC"
    assert refuse.mode == "flavor"


def test_planner_only_outputs_allowed_kinds():
    sheet = generate_npc_sheet("n2", "Planner NPC", "town_square", tier=3, llm_client=None)
    state = initial_state_for_sheet(sheet)
    obs = Observation(now_ts=10, location_id="town_square", location_name="Asterfall Commons")
    output = plan_npc_tick(sheet, state, obs, rng=random.Random(7))
    assert output.intent == "npc_tick"
    assert output.candidate_actions
    for action in output.candidate_actions:
        assert action.kind in ALLOWED_TICK_KINDS
