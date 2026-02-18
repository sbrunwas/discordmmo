from __future__ import annotations


def death_save_roll(seed_value: int) -> int:
    return (seed_value % 20) + 1
