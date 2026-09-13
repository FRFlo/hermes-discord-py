"""Discord thread update listener."""

import logging

from discord.ext import commands

logger = logging.getLogger("plugins.platforms.discord.adapter")


class ThreadUpdateEvent(commands.Cog):
    def __init__(self, adapter) -> None:
        self.adapter = adapter

    @commands.Cog.listener()
    async def on_thread_update(self, before, after) -> None:
        adapter = self.adapter
        old_name = getattr(before, "name", None)
        new_name = getattr(after, "name", None)
        thread_id = getattr(after, "id", None)
        owner_id = getattr(after, "owner_id", None)
        if (
            old_name == new_name
            or not isinstance(new_name, str)
            or thread_id is None
            or owner_id is None
        ):
            return
        parent_id = getattr(after, "parent_id", None)
        guild = getattr(after, "guild", None)
        event = {
            "platform": "discord",
            "event_type": "thread_renamed",
            "payload": {
                "thread_id": str(thread_id)[:128],
                "parent_chat_id": str(parent_id)[:128] if parent_id is not None else None,
                "old_name": old_name[:256] if isinstance(old_name, str) else None,
                "new_name": new_name[:256],
            },
        }
        source = adapter.build_source(
            chat_id=str(thread_id), chat_type="thread", user_id=str(owner_id),
            user_name=None, thread_id=str(thread_id),
            guild_id=str(getattr(guild, "id", "")) if guild else None,
        )
        handler = getattr(adapter, "_platform_event_handler", None)
        if handler is None:
            return
        try:
            await handler(event, source)
        except Exception:
            logger.debug("[%s] thread update dispatch error", adapter.name, exc_info=True)
