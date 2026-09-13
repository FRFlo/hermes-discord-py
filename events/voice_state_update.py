"""Discord voice state update listener."""

import logging

from discord.ext import commands

logger = logging.getLogger("plugins.platforms.discord.adapter")


class VoiceStateUpdateEvent(commands.Cog):
    def __init__(self, adapter) -> None:
        self.adapter = adapter

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after) -> None:
        adapter = self.adapter
        bot_guild_ids = set(adapter._voice_clients.keys())
        if not bot_guild_ids:
            return
        guild_id = member.guild.id
        if guild_id not in bot_guild_ids or member == adapter._client.user:
            return
        joined = before.channel is None and after.channel is not None
        left = before.channel is not None and after.channel is None
        switched = (
            before.channel is not None
            and after.channel is not None
            and before.channel != after.channel
        )
        if joined or left or switched:
            logger.info(
                "Voice state: %s (%d) %s (guild %d)", member.display_name, member.id,
                "joined " + after.channel.name if joined
                else "left " + before.channel.name if left
                else f"moved {before.channel.name} -> {after.channel.name}", guild_id,
            )
