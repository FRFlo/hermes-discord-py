"""On-demand, ephemeral display of a completed turn's tool trace."""

from __future__ import annotations

import json
from typing import Any


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
            lines.append(f"\n**{name}**\n```json\n{json.dumps(arguments, ensure_ascii=False, indent=2, default=str)[:3500]}\n```")
        if message.get("role") == "tool":
            found = True
            result = str(message.get("content") or "")
            lines.append(f"**Result**\n```\n{result[:3500]}\n```")
    if not found:
        return "No tool trace is available for this response."
    return "\n".join(lines)[:5900]


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
                    text = get_tool_trace_text(adapter, str(session_key))
                    await interaction.response.send_message(text, ephemeral=True)
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
