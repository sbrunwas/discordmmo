from __future__ import annotations

from app.db.store import Store
from app.models.proposals import Proposal


ALLOWED = {"SIDE_QUEST", "ATTITUDE_SHIFT", "DIALOGUE_UNLOCK", "FACTION_SENTIMENT", "RUMOR"}


def submit_proposal(store: Store, proposal: Proposal) -> bool:
    if proposal.proposal_type not in ALLOWED:
        return False
    store.add_proposal(proposal.actor_id, proposal.proposal_type, proposal.content)
    store.write_event(proposal.actor_id, "PROPOSAL_SUBMITTED", proposal.model_dump())
    return True
