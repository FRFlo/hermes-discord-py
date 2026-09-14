"""On-demand, ephemeral display of a completed turn's tool trace."""

from __future__ import annotations

import asyncio
import json
from typing import Any


def _safe_code_name(value: Any) -> str:
    return str(value or "tool").replace("`", "ˋ")


def _compact_call_arguments(arguments: Any) -> str:
    """Return JSON arguments in a readable function-call form."""
    if not isinstance(arguments, dict):
        return json.dumps(arguments, ensure_ascii=False, separators=(",", ":"), default=str)
    return ", ".join(
        f"{key}={json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str)}"
        for key, value in arguments.items()
    )


def _trace_text(messages: list[dict[str, Any]]) -> str:
    """Render tool calls and results from the persisted session transcript."""
    # A button belongs to the latest assistant response, not the entire session.
    last_user = max((i for i, item in enumerate(messages)
                     if isinstance(item, dict) and item.get("role") == "user"), default=-1)
    messages = messages[last_user + 1:]
    lines: list[str] = ["🔎 **Tool trace**"]
    found = False
    for message in messages:
        if not isinstance(message, dict):
            continue
        for call in message.get("tool_calls") or []:
            function = call.get("function") if isinstance(call, dict) else None
            if not isinstance(function, dict):
                continue
            found = True
            name = function.get("name") or "tool"
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except (TypeError, ValueError):
                    pass
            lines.append(_format_tool_call(name, arguments))
        if message.get("role") == "tool":
            found = True
            result = str(message.get("content") or "")
            lines.append(_format_tool_result(result))
    if not found:
        return "No tool trace is available for this response."
    return "\n".join(lines)


def split_discord_messages(text: str, *, limit: int = 1900) -> list[str]:
    """Split trace text below Discord's 2000-character limit.

    Prefer line boundaries, but hard-split unusually long tool output lines so
    every follow-up remains sendable. A margin is intentional: it leaves room
    for Discord/API wrappers without relying on the exact platform ceiling.
    """
    if not text:
        return []
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current.rstrip("\n"))
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if current and len(current) + len(line) > limit:
            chunks.append(current.rstrip("\n"))
            current = ""
        current += line
    if current:
        chunks.append(current.rstrip("\n"))
    return chunks


async def send_ephemeral_trace(interaction: Any, text: str) -> None:
    """Send a long trace as one initial ephemeral response plus follow-ups."""
    chunks = split_discord_messages(text)
    if not chunks:
        chunks = ["No tool trace is available for this response."]
    await interaction.response.send_message(chunks[0], ephemeral=True)
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk, ephemeral=True)


def _tracked_response_key(adapter: Any, target_message: Any, session_key: str) -> Any:
    target_id = str(getattr(target_message, "id", "") or "")
    tracked = getattr(adapter, "_hermes_response_message_ids", {})
    return next(
        (key for key, ids in reversed(list(tracked.items()))
         if key[0] == str(session_key) and target_id in ids),
        None,
    )


async def delete_response_turn_from_session(
    adapter: Any, session_key: str, inbound_id: str,
) -> bool:
    """Remove the selected user/assistant turn while preserving later turns."""
    store = getattr(adapter, "_session_store", None)
    entry = store.lookup_by_session_key(str(session_key)) if store is not None else None
    if entry is None:
        return False

    history = await asyncio.to_thread(store.load_transcript, entry.session_id)
    start = next(
        (index for index, message in enumerate(history)
         if message.get("role") == "user" and str(message.get("message_id") or "") == str(inbound_id)),
        None,
    )
    if start is None:
        return False
    end = next(
        (index for index in range(start + 1, len(history)) if history[index].get("role") == "user"),
        len(history),
    )
    rewritten = [*history[:start], *history[end:]]
    changed = await asyncio.to_thread(
        store.rewrite_transcript, entry.session_id, rewritten,
        active_only=True, reject_active_turn_lease=True,
    )
    if not changed:
        return False
    entry.last_prompt_tokens = 0
    runner = getattr(adapter, "gateway_runner", None)
    evict = getattr(runner, "_evict_cached_agent", None)
    if callable(evict):
        evict(str(session_key))
    return True


async def delete_tracked_response(
    adapter: Any, target_message: Any, session_key: str, *, delete_session: bool = False,
) -> None:
    """Delete every Discord chunk belonging to the selected assistant response."""
    target_id = str(getattr(target_message, "id", "") or "")
    tracked = getattr(adapter, "_hermes_response_message_ids", {})
    response_key = _tracked_response_key(adapter, target_message, session_key)
    if delete_session:
        if response_key is None or not await delete_response_turn_from_session(
            adapter, str(session_key), str(response_key[1]),
        ):
            raise RuntimeError("Could not remove the selected response from the session")
    message_ids = list(tracked.pop(response_key, [])) if response_key is not None else []
    if target_id and target_id not in message_ids:
        message_ids.append(target_id)

    channel_id = str(getattr(getattr(target_message, "channel", None), "id", "") or "")
    for message_id in message_ids:
        if channel_id:
            await adapter.delete_message(channel_id, message_id)

    session_keys = getattr(adapter, "_hermes_session_keys_by_message_id", {})
    for message_id in message_ids:
        session_keys.pop(str(message_id), None)


def _format_tool_call(name: Any, arguments: Any, *, inline_limit: int = 180) -> str:
    """Render a persisted call like the model's function-call representation."""
    safe_name = _safe_code_name(name)
    if not arguments:
        return f"\n⚙️ `{safe_name}()`"

    compact = _compact_call_arguments(arguments)
    if len(safe_name) + len(compact) + 5 <= inline_limit:
        return f"\n⚙️ `{safe_name}({compact})`"

    payload = json.dumps(arguments, ensure_ascii=False, indent=2, default=str)
    return f"\n⚙️ `{safe_name}`(\n```json\n{payload[:3500]}\n```\n)"


def format_live_tool_call(event: Any, *, mode: str = "all", preview_max_len: int = 40) -> str | None:
    """Render a Hermes ToolCallChunk as Discord Markdown.

    ``off`` is normally filtered by Hermes before this function is called, but
    handling it here keeps the adapter safe when called directly by tests or
    integrations. ``new`` deduplication and ``log`` routing remain gateway
    responsibilities.
    """
    if mode in {"off", "log"}:
        return None
    name = _safe_code_name(getattr(event, "tool_name", None))
    arguments = getattr(event, "args", None) or {}
    if mode == "verbose":
        return _format_tool_call(name, arguments, inline_limit=0)
    limit = preview_max_len if preview_max_len > 0 else 40
    return _format_tool_call(name, arguments, inline_limit=max(40, limit))


def _format_tool_result(result: str) -> str:
    """Keep results visibly attached to the preceding code-style call."""
    # A result can contain a fence of its own; using a longer fence keeps the
    # trace readable instead of prematurely closing the Discord code block.
    fence = "````" if "```" in result else "```"
    return f"↳ **Result**\n{fence}\n{result[:3500]}\n{fence}"


def build_tool_trace_view(discord_module: Any, adapter: Any, session_key: str) -> Any:
    """Build the persistent actions attached to a completed assistant response.

    The regenerate action deliberately goes through the existing ``/retry`` command
    instead of replaying the transcript here.  That keeps the gateway's retry
    semantics (including the original user prompt and session context) in one place.
    """
    class ConfirmationView(discord_module.ui.View):
        """Ephemeral confirmation prompt for destructive/expensive actions."""

        def __init__(self, action: Any, *, confirm_label: str) -> None:
            super().__init__(timeout=60)
            self._action = action
            self.add_item(self.ConfirmButton(confirm_label))
            self.add_item(self.CancelButton())

        class ConfirmButton(discord_module.ui.Button):
            def __init__(self, label: str) -> None:
                super().__init__(label=label, style=discord_module.ButtonStyle.danger,
                                 custom_id=f"hermes:confirm:{session_key}")

            async def callback(self, interaction: Any) -> None:
                try:
                    await self.view._action(interaction)
                except Exception:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(
                            "L’action a échoué. Vous pouvez réessayer.", ephemeral=True)
                    else:
                        await interaction.followup.send(
                            "L’action a échoué. Vous pouvez réessayer.", ephemeral=True)

        class CancelButton(discord_module.ui.Button):
            def __init__(self) -> None:
                super().__init__(label="Annuler", style=discord_module.ButtonStyle.secondary,
                                 custom_id=f"hermes:cancel:{session_key}")

            async def callback(self, interaction: Any) -> None:
                await interaction.response.edit_message(
                    content="Action annulée.", view=None)

    class ToolTraceView(discord_module.ui.View):
        def __init__(self) -> None:
            super().__init__(timeout=None)
            self.add_item(self.ShowTraceButton())
            self.add_item(self.RegenerateButton())
            self.add_item(self.ContinueButton())
            self.add_item(self.DeleteButton())

        class ShowTraceButton(discord_module.ui.Button):
            def __init__(self) -> None:
                super().__init__(label="Afficher le raisonnement", style=discord_module.ButtonStyle.secondary,
                                 custom_id=f"hermes:trace:{session_key}")

            async def callback(self, interaction: Any) -> None:
                try:
                    await send_ephemeral_trace(
                        interaction, get_tool_trace_text(adapter, str(session_key)),
                    )
                except Exception:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(
                            "Le détail de cette réponse n’est plus disponible.", ephemeral=True)

        class RegenerateButton(discord_module.ui.Button):
            def __init__(self) -> None:
                super().__init__(label="Tout régénérer", style=discord_module.ButtonStyle.primary,
                                 custom_id=f"hermes:regenerate:{session_key}")

            async def callback(self, interaction: Any) -> None:
                try:
                    if not await adapter._check_slash_authorization(interaction, "/retry"):
                        return

                    target_message = getattr(interaction, "message", None)

                    async def regenerate(confirmed_interaction: Any) -> None:
                        response_key = _tracked_response_key(
                            adapter, target_message, str(session_key),
                        )
                        if response_key is None:
                            raise RuntimeError("Could not identify the response to regenerate")
                        await confirmed_interaction.response.edit_message(
                            content="La réponse va être régénérée.", view=None,
                        )
                        await delete_tracked_response(adapter, target_message, str(session_key))
                        # /retry atomically removes the previous user/assistant turn from
                        # the transcript before replaying the original user message.
                        event = adapter._build_slash_event(confirmed_interaction, "/retry")
                        chat_id = str(getattr(getattr(target_message, "channel", None), "id", "") or "")
                        pending = getattr(adapter, "_hermes_pending_response_turns", None)
                        if pending is None:
                            pending = adapter._hermes_pending_response_turns = {}
                        pending[chat_id] = (str(session_key), str(response_key[1]))
                        try:
                            await adapter.handle_message(event)
                        finally:
                            pending.pop(chat_id, None)

                    await interaction.response.send_message(
                        "Voulez-vous vraiment régénérer toute la réponse ?",
                        ephemeral=True,
                        view=ConfirmationView(regenerate, confirm_label="Régénérer"),
                    )
                except Exception:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(
                            "La régénération a échoué. Vous pouvez réessayer.", ephemeral=True)

        class ContinueButton(discord_module.ui.Button):
            def __init__(self) -> None:
                super().__init__(label="Continuer", style=discord_module.ButtonStyle.secondary,
                                 custom_id=f"hermes:continue:{session_key}")

            async def callback(self, interaction: Any) -> None:
                # A normal text event keeps the current session and transcript,
                # so the agent receives the same context as a typed follow-up.
                try:
                    await adapter._run_simple_slash(
                        interaction, "Continue.", "Je continue~",
                    )
                except Exception:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(
                            "Impossible de continuer cette réponse.", ephemeral=True)

        class DeleteButton(discord_module.ui.Button):
            def __init__(self) -> None:
                super().__init__(label="Supprimer", style=discord_module.ButtonStyle.danger,
                                 custom_id=f"hermes:delete:{session_key}")

            async def callback(self, interaction: Any) -> None:
                try:
                    if not await adapter._check_slash_authorization(interaction, "/delete"):
                        return

                    target_message = getattr(interaction, "message", None)

                    async def delete(confirmed_interaction: Any) -> None:
                        await confirmed_interaction.response.defer(ephemeral=True)
                        await delete_tracked_response(
                            adapter, target_message, str(session_key), delete_session=True,
                        )
                        await confirmed_interaction.followup.send(
                            "Réponse supprimée.", ephemeral=True)

                    await interaction.response.send_message(
                        "Voulez-vous vraiment supprimer cette réponse ?",
                        ephemeral=True,
                        view=ConfirmationView(delete, confirm_label="Supprimer"),
                    )
                except Exception:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(
                            "Impossible de supprimer cette réponse.", ephemeral=True)

    return ToolTraceView()


def get_tool_trace_text(adapter: Any, session_key: str) -> str:
    """Load a trace from the existing session store, or return a safe fallback."""
    store = getattr(adapter, "_session_store", None)
    entry = store.lookup_by_session_key(str(session_key)) if store is not None else None
    transcript = store.load_transcript(entry.session_id) if entry is not None else []
    return _trace_text(transcript)
