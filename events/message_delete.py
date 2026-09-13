"""Discord raw message delete listener."""

import logging

from discord.ext import commands

logger = logging.getLogger("plugins.platforms.discord.adapter")


class MessageDeleteEvent(commands.Cog):
    def __init__(self, adapter) -> None:
        self.adapter = adapter

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload) -> None:
        adapter = self.adapter
        message_id = getattr(payload, "message_id", None)
        if message_id is None:
            return
        identity = adapter._platform_message_identities.pop(str(message_id), None)
        cached_message = getattr(payload, "cached_message", None)
        author = getattr(cached_message, "author", None)
        if identity is None and cached_message is not None:
            channel = (
                getattr(cached_message, "thread", None)
                or getattr(cached_message, "channel", None)
            )
            channel_id = getattr(channel, "id", None)
            guild = getattr(cached_message, "guild", None)
            is_thread = (
                getattr(channel, "parent_id", None) is not None
                or getattr(cached_message, "thread", None) is not None
            )
            identity = {
                "chat_id": str(channel_id) if channel_id is not None else None,
                "chat_type": "thread" if is_thread else ("dm" if guild is None else "group"),
                "thread_id": str(channel_id) if is_thread and channel_id is not None else None,
                "guild_id": str(getattr(guild, "id", "")) if guild else None,
                "user_id": str(getattr(author, "id", "") or "") or None,
                "user_name": getattr(author, "display_name", None),
                "author_is_bot": bool(getattr(author, "bot", False)),
            }
        if identity is None or identity["chat_id"] is None or not identity["user_id"]:
            return
        is_bot = bool(identity["author_is_bot"])
        if is_bot and not getattr(adapter, "_platform_event_sync_enabled", False):
            return

        event_payload = {
            "chat_id": identity["chat_id"][:128],
            "message_id": str(message_id)[:128],
            "thread_id": identity["thread_id"][:128] if identity["thread_id"] else None,
            "author_id": identity["user_id"][:128],
        }
        if is_bot:
            event_payload["author_is_bot"] = True
        event = {"platform": "discord", "event_type": "message_deleted", "payload": event_payload}
        source = adapter.build_source(
            chat_id=identity["chat_id"], chat_type=identity["chat_type"],
            user_id=identity["user_id"], user_name=identity["user_name"],
            thread_id=identity["thread_id"], guild_id=identity["guild_id"],
            message_id=str(message_id),
        )
        handler = getattr(adapter, "_platform_event_handler", None)
        if handler is None:
            return
        try:
            await handler(event, source)
        except Exception:
            logger.debug("[%s] message delete dispatch error", adapter.name, exc_info=True)
