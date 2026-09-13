"""Discord raw message edit listener."""

import logging

from discord.ext import commands

logger = logging.getLogger("plugins.platforms.discord.adapter")


class MessageEditEvent(commands.Cog):
    def __init__(self, adapter) -> None:
        self.adapter = adapter

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload) -> None:
        adapter = self.adapter
        data = getattr(payload, "data", None)
        if isinstance(data, dict) and "content" not in data:
            return
        message = getattr(payload, "message", None) or getattr(payload, "cached_message", None)
        if message is None:
            return
        author = getattr(message, "author", None)
        message_id = getattr(message, "id", None)
        identity = adapter._platform_message_identities.get(str(message_id))
        author_is_bot = bool(
            identity["author_is_bot"] if identity is not None else getattr(author, "bot", False)
        )
        if author_is_bot:
            return

        channel = getattr(message, "thread", None) or getattr(message, "channel", None)
        guild = getattr(message, "guild", None)
        channel_id = getattr(channel, "id", None)
        if identity is None:
            is_thread = (
                getattr(channel, "parent_id", None) is not None
                or getattr(message, "thread", None) is not None
            )
            identity = {
                "chat_id": str(channel_id) if channel_id is not None else None,
                "chat_type": "thread" if is_thread else ("dm" if guild is None else "group"),
                "thread_id": str(channel_id) if is_thread and channel_id is not None else None,
                "guild_id": str(getattr(guild, "id", "")) if guild else None,
                "user_id": str(getattr(author, "id", "") or "") or None,
                "user_name": getattr(author, "display_name", None),
            }
        if identity["chat_id"] is None or message_id is None or not identity["user_id"]:
            return

        text = getattr(message, "content", None)
        edited_at = getattr(message, "edited_at", None)
        event = {
            "platform": "discord",
            "event_type": "message_edited",
            "payload": {
                "chat_id": identity["chat_id"][:128],
                "message_id": str(message_id)[:128],
                "thread_id": identity["thread_id"][:128] if identity["thread_id"] else None,
                "text": text[:8192] if isinstance(text, str) else None,
                "edited_at": (
                    str(edited_at.isoformat())[:64]
                    if edited_at is not None and hasattr(edited_at, "isoformat") else None
                ),
            },
        }
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
            logger.debug("[%s] message edit dispatch error", adapter.name, exc_info=True)
