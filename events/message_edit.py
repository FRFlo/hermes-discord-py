"""Discord ``on_message_edit`` event."""


async def handle(before, after, adapter) -> None:
    """Normalize an edited user message into the platform-event boundary."""
    def extra(message, author):
        text = getattr(message, "content", None)
        edited_at = getattr(message, "edited_at", None)
        return {
            "text": text[:8192] if isinstance(text, str) else None,
            "edited_at": str(edited_at.isoformat())[:64] if edited_at is not None and hasattr(edited_at, "isoformat") else None,
        }

    message = after if after is not None else before
    await adapter._emit_platform_event(
        "message_edited", lambda: adapter._message_event_parts(message, extra),
    )


async def handle_raw(payload, adapter) -> None:
    """Handle edits even when Discord evicted the original message from cache."""
    data = getattr(payload, "data", None)
    if isinstance(data, dict) and "content" not in data:
        return  # embed/link-preview updates are not user text edits
    message = getattr(payload, "message", None) or getattr(payload, "cached_message", None)
    if message is None:
        return
    await handle(getattr(payload, "cached_message", None), message, adapter)


def register(client, adapter) -> None:
    @client.event
    async def on_raw_message_edit(payload):
        await handle_raw(payload, adapter)
