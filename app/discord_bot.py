from __future__ import annotations

import logging

from app.engine.world_engine import WorldEngine

log = logging.getLogger(__name__)

try:
    import discord
except Exception:  # pragma: no cover
    discord = None


def run_bot(token: str, engine: WorldEngine) -> None:
    if discord is None:
        raise RuntimeError("discord.py not installed")
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_message(message):
        if message.author.bot:
            return
        result = engine.handle_message(str(message.author.id), message.author.display_name, message.content)
        await message.channel.send(result.message)

    log.info("starting_discord_bot")
    client.run(token)
