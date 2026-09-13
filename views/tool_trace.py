"""On-demand, ephemeral display of a completed turn's tool trace."""

from __future__ import annotations

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

                    async def regenerate(confirmed_interaction: Any) -> None:
                        # _run_simple_slash performs the normal authorization gate and
                        # defers the interaction before starting the potentially long turn.
                        await adapter._run_simple_slash(
                            confirmed_interaction, "/retry", "Régénération en cours~",
                        )

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
                        if target_message is not None and hasattr(target_message, "delete"):
                            await target_message.delete()
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
