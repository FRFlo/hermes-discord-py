import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from events import register_events
from events.interaction import InteractionEvent
from events.message_create import MessageCreateEvent
from events.message_delete import MessageDeleteEvent
from events.message_edit import MessageEditEvent
from events.ready import ReadyEvent
from events.thread_create import ThreadCreateEvent
from events.thread_update import ThreadUpdateEvent
from events.voice_state_update import VoiceStateUpdateEvent


def _adapter():
    handler = AsyncMock()
    adapter = SimpleNamespace(
        name="Discord",
        _platform_event_handler=handler,
        _platform_event_sync_enabled=True,
        _platform_message_identities={},
        build_source=lambda **kwargs: SimpleNamespace(**kwargs),
    )
    return adapter, handler


def _message(*, message_id=123, channel_id=10, guild_id=20, content="edited", thread=None):
    return SimpleNamespace(
        id=message_id,
        channel=SimpleNamespace(id=channel_id, parent_id=None),
        thread=thread,
        guild=SimpleNamespace(id=guild_id) if guild_id is not None else None,
        author=SimpleNamespace(id=30, display_name="user", bot=False),
        content=content,
        edited_at=None,
    )


def test_event_cogs_declare_native_discord_listeners():
    adapter, _handler = _adapter()
    listeners = {
        name
        for event_cog in (
            ReadyEvent, MessageCreateEvent, MessageEditEvent, MessageDeleteEvent,
            ThreadCreateEvent, ThreadUpdateEvent, VoiceStateUpdateEvent, InteractionEvent,
        )
        for name, _callback in event_cog(adapter).get_listeners()
    }

    assert listeners == {
        "on_interaction", "on_message", "on_raw_message_delete", "on_raw_message_edit", "on_ready",
        "on_thread_create", "on_thread_update", "on_voice_state_update",
    }


def test_event_cogs_are_registered_explicitly_with_discord_py():
    adapter, _handler = _adapter()
    bot = SimpleNamespace(add_cog=AsyncMock())

    asyncio.run(register_events(bot, adapter))

    registered = [call.args[0] for call in bot.add_cog.await_args_list]
    assert [type(cog) for cog in registered] == [
        ReadyEvent, MessageCreateEvent, MessageEditEvent, MessageDeleteEvent,
        ThreadCreateEvent, ThreadUpdateEvent, VoiceStateUpdateEvent, InteractionEvent,
    ]


def test_raw_edit_forwards_discord_payload_directly():
    adapter, handler = _adapter()
    create_event = MessageCreateEvent(adapter)
    edit_event = MessageEditEvent(adapter)
    message = _message()
    create_event._remember_message(message)
    payload = SimpleNamespace(data={"content": "edited"}, message=message, cached_message=None)

    asyncio.run(edit_event.on_raw_message_edit(payload))

    handler.assert_awaited_once()
    event, source = handler.await_args.args
    assert event["event_type"] == "message_edited"
    assert event["payload"]["text"] == "edited"
    assert source.chat_type == "group"


def test_raw_edit_ignores_embed_only_update():
    adapter, handler = _adapter()
    edit_event = MessageEditEvent(adapter)
    payload = SimpleNamespace(data={"embeds": []}, message=_message(), cached_message=None)

    asyncio.run(edit_event.on_raw_message_edit(payload))

    handler.assert_not_awaited()


def test_raw_delete_uses_identity_recorded_by_message_event():
    adapter, handler = _adapter()
    create_event = MessageCreateEvent(adapter)
    delete_event = MessageDeleteEvent(adapter)
    message = _message()
    create_event._remember_message(message)
    payload = SimpleNamespace(message_id=message.id, cached_message=None)

    asyncio.run(delete_event.on_raw_message_delete(payload))

    event, source = handler.await_args.args
    assert event["event_type"] == "message_deleted"
    assert event["payload"]["message_id"] == "123"
    assert source.chat_id == "10"


def test_thread_create_routes_starter_message_mutations_to_thread():
    adapter, handler = _adapter()
    create_event = MessageCreateEvent(adapter)
    thread_event = ThreadCreateEvent(adapter)
    edit_event = MessageEditEvent(adapter)
    message = _message(message_id=123)
    create_event._remember_message(message)
    thread = SimpleNamespace(
        id=123, owner_id=30, parent_id=10, name="thread", guild=SimpleNamespace(id=20),
    )

    asyncio.run(thread_event.on_thread_create(thread))
    payload = SimpleNamespace(data={"content": "edited"}, message=message, cached_message=None)
    asyncio.run(edit_event.on_raw_message_edit(payload))

    edit_event, edit_source = handler.await_args_list[-1].args
    assert edit_event["payload"]["chat_id"] == "123"
    assert edit_source.chat_type == "thread"
    assert edit_source.thread_id == "123"


def test_message_identity_preserves_dm_chat_type():
    adapter, _handler = _adapter()
    create_event = MessageCreateEvent(adapter)

    create_event._remember_message(_message(guild_id=None))

    assert adapter._platform_message_identities["123"]["chat_type"] == "dm"
