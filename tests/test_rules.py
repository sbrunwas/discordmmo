from app.engine.rules_engine import death_save_roll


def test_death_save_roll_range():
    assert death_save_roll(1) == 2
    assert death_save_roll(39) == 20
