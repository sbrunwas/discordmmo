import random

from app.engine.rules_engine import death_save_roll


def test_death_save_roll_range():
    rng = random.Random(7)
    for _ in range(20):
        roll = death_save_roll(rng)
        assert 1 <= roll <= 20
