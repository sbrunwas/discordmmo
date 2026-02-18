from __future__ import annotations

import logging
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("DB_PATH", "mmo.db")
    dev_mode: bool = os.getenv("DEV_MODE", "0") == "1"
    discord_token: str | None = os.getenv("DISCORD_TOKEN")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    rng_seed: int = int(os.getenv("RNG_SEED", "1337"))


def configure_logging(dev_mode: bool) -> None:
    level = logging.DEBUG if dev_mode else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
