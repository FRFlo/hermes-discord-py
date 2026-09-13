"""Discord thread creation listener."""

import logging

from discord.ext import commands

logger = logging.getLogger("plugins.platforms.discord.adapter")


class ThreadCreateEvent(commands.Cog):
    def __init__(self, adapter) -> None:
        self.adapter = adapter

    @commands.Cog.listener()
    async def on_thread_create(self, thread) -> None:
        adapter = self.adapter
        thread_id = getattr(thread, "id", None)
        owner_id = getattr(thread, "owner_id", None)
        if thread_id is None or owner_id is None:
            return
        identity = adapter._platform_message_identities.get(str(thread_id))
        if identity is not None:
            identity["chat_id"] = str(thread_id)
            identity["chat_type"] = "thread"
            identity["thread_id"] = str(thread_id)

        parent_id = getattr(thread, "parent_id", None)
        guild = getattr(thread, "guild", None)
        thread_name = getattr(thread, "name", None)
        event = {
            "platform": "discord",
            "event_type": "thread_created",
            "payload": {
                "thread_id": str(thread_id)[:128],
                "parent_chat_id": str(parent_id)[:128] if parent_id is not None else None,
                "name": thread_name[:256] if isinstance(thread_name, str) else None,
                "owner_id": str(owner_id)[:128],
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
            logger.debug("[%s] thread create dispatch error", adapter.name, exc_info=True)
