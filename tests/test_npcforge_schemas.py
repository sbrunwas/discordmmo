from __future__ import annotations

from app.npcforge.schemas import CandidateAction, NPCOutput, NPCSheet, NPCState, Observation, OutcomeFeedback


def test_npcforge_schema_roundtrip():
    sheet = NPCSheet(
        npc_id="npc_1",
        name="Ruin Warden",
        alignment="lawful_good",
        background_paragraphs=["Paragraph one.", "Paragraph two."],
        ideals=["Duty"],
        bonds=["The town"],
        flaws=["Overcautious"],
        motivation="Protect the commons.",
        fear="Another breach.",
        archetype="Warden",
        skills=["observation", "mediation"],
        voice_style="Calm and direct.",
        allowed_locations=["town_square", "ruin_upper"],
        tier=3,
    )
    state = NPCState()
    obs = Observation(now_ts=1, location_id="town_square", location_name="Asterfall Commons", player_id="p1")
    feedback = OutcomeFeedback(what_happened="Player helped.", emotional_reaction="Relief", ts=1)
    output = NPCOutput(
        dialogue="Thank you.",
        intent="maintain_relationship",
        candidate_actions=[CandidateAction(kind="help", content="Provide directions")],
        state_updates={"mood": 1},
        memory_update=feedback,
    )

    assert NPCSheet(**sheet.model_dump()).name == "Ruin Warden"
    assert NPCState(**state.model_dump()).mood == 0
    assert Observation(**obs.model_dump()).player_id == "p1"
    assert NPCOutput(**output.model_dump()).candidate_actions[0].kind == "help"
