from __future__ import annotations

import random


def death_save_roll(rng: random.Random) -> int:
    return rng.randint(1, 20)
