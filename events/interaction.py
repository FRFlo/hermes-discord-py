"""Discord interaction listener."""

from discord.ext import commands


class InteractionEvent(commands.Cog):
    def __init__(self, adapter) -> None:
        self.adapter = adapter

    @commands.Cog.listener()
    async def on_interaction(self, interaction) -> None:
        await self.adapter._on_tool_trace_interaction(interaction)

