"""Small compatibility helpers for Discord Components V2 payloads.

Components V2 messages cannot carry legacy ``content`` or embeds.  Keeping the
conversion here lets the interaction builders continue to describe prompts in
the same form while the sender chooses a V2 payload when discord.py supports
it.  The fallback is deliberately legacy-shaped for older test doubles and
discord.py releases.
"""

from __future__ import annotations

from typing import Any, Optional


def components_v2_available(discord_module: Any) -> bool:
    """Return whether the loaded discord.py exposes the V2 view primitives."""
    ui = getattr(discord_module, "ui", None)
    return bool(ui and getattr(ui, "LayoutView", None) and getattr(ui, "TextDisplay", None))


def text_from_payload(send_kwargs: dict[str, Any]) -> str:
    """Build an accessible plain-text representation of a prompt payload."""
    content = str(send_kwargs.get("content") or "").strip()
    embed = send_kwargs.get("embed")
    if embed is not None:
        title = str(getattr(embed, "title", "") or "").strip()
        description = str(getattr(embed, "description", "") or "").strip()
        fields = []
        for field in getattr(embed, "fields", ()) or ():
            name = str(getattr(field, "name", "") or "").strip()
            value = str(getattr(field, "value", "") or "").strip()
            if name and value:
                fields.append(f"{name}: {value}")
        pieces = [piece for piece in (title, description, *fields) if piece]
        if pieces:
            embed_text = "\n\n".join(pieces)
            if content and embed_text not in content:
                return f"{content}\n\n{embed_text}"
            return content or embed_text
    return content


def install_text_display(view: Any, text: str) -> bool:
    """Add the prompt's text to a V2 view, returning whether it was installed."""
    if not text or not hasattr(view, "add_item"):
        return False
    if len(text) > 4000:
        text = text[:3997] + "..."
    discord_module = getattr(view, "_discord_module", None)
    ui = getattr(discord_module, "ui", None)
    text_display = getattr(ui, "TextDisplay", None)
    if text_display is None:
        return False
    try:
        item = text_display(text)
        # Use the public insertion path so LayoutView keeps its child count valid,
        # then place text before controls already attached by the view constructor.
        view.add_item(item)
        view._children.remove(item)
        view._children.insert(0, item)
        view._v2_text_display = item
        return True
    except Exception:
        return False


def update_text_display(view: Any, text: str) -> bool:
    """Replace the text portion of a V2 view, if present."""
    item = getattr(view, "_v2_text_display", None)
    if item is None:
        return False
    item.content = text
    return True


def build_text_view(discord_module: Any, text: str) -> Optional[Any]:
    """Build a static V2 view for a message that has no interactive controls."""
    if not components_v2_available(discord_module):
        return None
    try:
        view = discord_module.ui.LayoutView(timeout=None)
        view._discord_module = discord_module
        return view if install_text_display(view, text) else None
    except Exception:
        return None


def build_media_view(discord_module: Any, text: str, files: list[Any]) -> Optional[Any]:
    """Build a V2 layout for captioned or attachment-only media."""
    if not components_v2_available(discord_module):
        return None
    try:
        view = discord_module.ui.LayoutView(timeout=None)
        view._discord_module = discord_module
        if text and not install_text_display(view, text):
            return None
        return view if add_file_components(view, discord_module, files) else None
    except Exception:
        return None


def add_file_components(view: Any, discord_module: Any, files: list[Any]) -> bool:
    """Reference uploaded files from a V2 view so Discord does not discard them."""
    file_component = getattr(getattr(discord_module, "ui", None), "File", None)
    if file_component is None or not hasattr(view, "add_item"):
        return False
    try:
        for file in files:
            filename = getattr(file, "filename", None)
            if not filename:
                return False
            view.add_item(file_component(f"attachment://{filename}"))
        return True
    except Exception:
        return False


def legacy_view_for(view: Any, discord_module: Any) -> Optional[Any]:
    """Copy V2 controls into a legacy View for a rejected V2 send."""
    view_class = getattr(getattr(discord_module, "ui", None), "View", None)
    if view_class is None:
        return None
    try:
        legacy = view_class(timeout=getattr(view, "timeout", None))
        for child in getattr(view, "children", ()):
            for nested in getattr(child, "children", ()):  # V2 ActionRow
                legacy.add_item(nested)
            if not getattr(child, "children", None) and child.__class__.__name__ != "TextDisplay":
                legacy.add_item(child)
        return legacy
    except Exception:
        return None

