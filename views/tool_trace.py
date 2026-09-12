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
    """Build a persistent-in-process button whose reply is Discord-ephemeral."""
    class ToolTraceView(discord_module.ui.View):
        def __init__(self) -> None:
            super().__init__(timeout=None)
            self.add_item(self.ShowTraceButton())

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

    return ToolTraceView()


def get_tool_trace_text(adapter: Any, session_key: str) -> str:
    """Load a trace from the existing session store, or return a safe fallback."""
    store = getattr(adapter, "_session_store", None)
    entry = store.lookup_by_session_key(str(session_key)) if store is not None else None
    transcript = store.load_transcript(entry.session_id) if entry is not None else []
    return _trace_text(transcript)
