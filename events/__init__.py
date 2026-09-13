"""Explicit registration of discord.py gateway event Cogs."""

from .interaction import InteractionEvent
from .message_create import MessageCreateEvent
from .message_delete import MessageDeleteEvent
from .message_edit import MessageEditEvent
from .ready import ReadyEvent
from .thread_create import ThreadCreateEvent
from .thread_update import ThreadUpdateEvent
from .voice_state_update import VoiceStateUpdateEvent


async def register_events(bot, adapter) -> None:
    """Register every Discord event Cog explicitly with discord.py."""
    for event_cog in (
        ReadyEvent,
        MessageCreateEvent,
        MessageEditEvent,
        MessageDeleteEvent,
        ThreadCreateEvent,
        ThreadUpdateEvent,
        VoiceStateUpdateEvent,
        InteractionEvent,
    ):
        await bot.add_cog(event_cog(adapter))


__all__ = ["register_events"]
