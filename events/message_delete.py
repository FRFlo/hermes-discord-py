"""Discord ``on_message_delete`` event."""


async def handle(message, adapter) -> None:
    """Normalize a deleted user message into the platform-event boundary."""
    def extra(_message, author):
        return {"author_id": str(getattr(author, "id", "") or "")[:128] or None}

    await adapter._emit_platform_event(
        "message_deleted",
        lambda: adapter._message_event_parts(
            message, extra, include_bot=getattr(adapter, "_platform_event_sync_enabled", False)
        ),
    )


async def handle_raw(payload, adapter) -> None:
    """Handle deletes independently of discord.py's internal message cache."""
    cached_message = getattr(payload, "cached_message", None)
    if cached_message is not None:
        identities = getattr(adapter, "_platform_message_identities", None)
        if identities is not None:
            identities.pop(str(getattr(payload, "message_id", "")), None)
        await handle(cached_message, adapter)
        return
    await adapter._emit_platform_event(
        "message_deleted",
        lambda: adapter._raw_message_delete_parts(
            payload, include_bot=getattr(adapter, "_platform_event_sync_enabled", False),
        ),
    )


def register(client, adapter) -> None:
    @client.event
    async def on_raw_message_delete(payload):
        await handle_raw(payload, adapter)
