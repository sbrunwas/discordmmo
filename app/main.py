from __future__ import annotations

import logging

from app.config import Settings, configure_logging
from app.db.store import Store
from app.discord_bot import run_discord_bot
from app.engine.world_engine import WorldEngine
from app.llm.client import LLMClient


def build_engine(settings: Settings) -> WorldEngine:
    store = Store(settings.db_path)
    engine = WorldEngine(store, LLMClient(settings, store=store), rng_seed=settings.rng_seed if settings.dev_mode else 42)
    engine.initialize_world()
    return engine


def main() -> None:
    settings = Settings()
    configure_logging(settings.dev_mode)
    logging.getLogger(__name__).info("app_start %s", settings.redacted())
    engine = build_engine(settings)
    run_discord_bot(engine, settings)


if __name__ == "__main__":
    main()
