from __future__ import annotations

import asyncio
import logging

from app.config import Settings
from app.engine.world_engine import WorldEngine

log = logging.getLogger(__name__)

try:
    import discord
except Exception:  # pragma: no cover
    discord = None


def run_discord_bot(engine: WorldEngine, settings: Settings) -> None:
    if discord is None:
        raise RuntimeError("discord.py not installed")
    if not settings.discord_token:
        raise RuntimeError("DISCORD_TOKEN is required to run the Discord bot")

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready() -> None:
        user_name = str(client.user) if client.user else "unknown"
        log.info("logged_in_as=%s", user_name)

    @client.event
    async def on_message(message) -> None:
        if message.author == client.user:
            return
        channel_name = getattr(message.channel, "name", "")
        if channel_name != "bot":
            return
        result = await asyncio.to_thread(
            engine.handle_message,
            str(message.author.id),
            message.author.display_name,
            message.content,
        )
        await message.channel.send(result.message)

    log.info("starting_discord_bot")
    client.run(settings.discord_token)


def run_bot(token: str, engine: WorldEngine) -> None:
    settings = Settings(discord_token=token)
    run_discord_bot(engine, settings)
