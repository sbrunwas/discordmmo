from __future__ import annotations

from app.db.store import Store

MILESTONES = [
    "whispering_stairs",
    "astral_lens",
    "vault_glyph",
    "branch_sun",
    "branch_moon",
    "convergence_gate",
]


def initialize_arc(store: Store) -> None:
    store.set_arc_value("season_arc", {"milestones": MILESTONES, "progress": [], "stuck_counter": 0})
