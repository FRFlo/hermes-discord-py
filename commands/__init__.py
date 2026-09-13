"""discord.py application-command Cogs."""

from .cog import HermesCommandsCog


async def register_command_cogs(bot, adapter) -> None:
    await bot.add_cog(HermesCommandsCog(adapter))


__all__ = ["register_command_cogs"]
