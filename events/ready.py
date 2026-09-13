"""Discord ready listener."""

import asyncio
import logging

from discord.ext import commands

logger = logging.getLogger("plugins.platforms.discord.adapter")


class ReadyEvent(commands.Cog):
    def __init__(self, adapter) -> None:
        self.adapter = adapter

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        adapter = self.adapter
        if adapter._ready_event.is_set():
            return
        logger.info("[%s] Connected as %s", adapter.name, adapter._client.user)
        await adapter._resolve_allowed_usernames()
        adapter._ready_event.set()
        if adapter._post_connect_task and not adapter._post_connect_task.done():
            adapter._post_connect_task.cancel()
        adapter._post_connect_task = asyncio.create_task(adapter._run_post_connect_initialization())
        if adapter._missed_message_backfill_enabled():
            adapter._ensure_missed_message_backfill_task()
