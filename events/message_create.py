"""Discord message creation listener."""

import asyncio

from discord.ext import commands


class MessageCreateEvent(commands.Cog):
    def __init__(self, adapter) -> None:
        self.adapter = adapter

    @commands.Cog.listener()
    async def on_message(self, message) -> None:
        adapter = self.adapter
        self._remember_message(message)
        if not adapter._ready_event.is_set():
            try:
                await asyncio.wait_for(adapter._ready_event.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                pass
        admitted, role_authorized = adapter._discord_message_admission(message, claim=True)
        if not admitted:
            return
        await adapter._handle_message(message, role_authorized=role_authorized)
        self._remember_message(message)

    def _remember_message(self, message) -> None:
        """Remember identity and routing required by raw deletion payloads."""
        message_id = getattr(message, "id", None)
        author = getattr(message, "author", None)
        channel = getattr(message, "thread", None) or getattr(message, "channel", None)
        channel_id = getattr(channel, "id", None)
        author_id = getattr(author, "id", None)
        if message_id is None or channel_id is None or author_id is None:
            return
        guild = getattr(message, "guild", None)
        is_thread = (
            getattr(channel, "parent_id", None) is not None
            or getattr(message, "thread", None) is not None
        )
        identities = self.adapter._platform_message_identities
        key = str(message_id)
        identities.pop(key, None)
        identities[key] = {
            "chat_id": str(channel_id),
            "chat_type": "thread" if is_thread else ("dm" if guild is None else "group"),
            "thread_id": str(channel_id) if is_thread else None,
            "guild_id": str(getattr(guild, "id", "")) if guild else None,
            "user_id": str(author_id),
            "user_name": getattr(author, "display_name", None),
            "author_is_bot": bool(getattr(author, "bot", False)),
        }
        if len(identities) > 4096:
            identities.pop(next(iter(identities)))
