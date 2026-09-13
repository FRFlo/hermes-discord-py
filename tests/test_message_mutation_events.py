import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from events import message_delete, message_edit


class _Client:
    def event(self, callback):
        setattr(self, callback.__name__, callback)
        return callback


def test_edit_registers_cache_independent_raw_event():
    client = _Client()
    adapter = SimpleNamespace(_emit_platform_event=AsyncMock(), _message_event_parts=MagicMock())

    message_edit.register(client, adapter)

    assert hasattr(client, "on_raw_message_edit")
    assert not hasattr(client, "on_message_edit")


def test_raw_edit_forwards_updated_message():
    message = SimpleNamespace(content="edited", edited_at=None)
    adapter = SimpleNamespace(_emit_platform_event=AsyncMock(), _message_event_parts=MagicMock(return_value=None))
    payload = SimpleNamespace(data={"content": "edited"}, message=message, cached_message=None)

    asyncio.run(message_edit.handle_raw(payload, adapter))

    adapter._emit_platform_event.assert_awaited_once()
    adapter._emit_platform_event.await_args.args[1]()
    adapter._message_event_parts.assert_called_once()
    assert adapter._message_event_parts.call_args.args[0] is message


def test_raw_edit_ignores_embed_only_update():
    adapter = SimpleNamespace(_emit_platform_event=AsyncMock(), _message_event_parts=MagicMock())
    payload = SimpleNamespace(data={"embeds": []}, message=SimpleNamespace(), cached_message=None)

    asyncio.run(message_edit.handle_raw(payload, adapter))

    adapter._emit_platform_event.assert_not_awaited()


def test_uncached_raw_delete_uses_identity_cache_normalizer():
    adapter = SimpleNamespace(
        _platform_event_sync_enabled=True,
        _emit_platform_event=AsyncMock(),
        _raw_message_delete_parts=MagicMock(return_value=None),
    )
    payload = SimpleNamespace(message_id=123, cached_message=None)

    asyncio.run(message_delete.handle_raw(payload, adapter))

    adapter._emit_platform_event.assert_awaited_once()
    adapter._emit_platform_event.await_args.args[1]()
    adapter._raw_message_delete_parts.assert_called_once_with(payload, include_bot=True)


def test_delete_registers_cache_independent_raw_event():
    client = _Client()
    adapter = SimpleNamespace()

    message_delete.register(client, adapter)

    assert hasattr(client, "on_raw_message_delete")
    assert not hasattr(client, "on_message_delete")
