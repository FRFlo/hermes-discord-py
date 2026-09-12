"""Shared plumbing for Discord component views."""

from __future__ import annotations

from typing import Optional

import discord

from .components_v2 import components_v2_available, text_from_payload, update_text_display

_ViewBase = (
    getattr(discord.ui, "LayoutView", discord.ui.View)
    if components_v2_available(discord)
    else discord.ui.View
)


class _HermesView(_ViewBase):
    """Shared plumbing for Hermes component views: allowlist auth, single-use
    ``resolved`` flag, ``_message`` handle for timeout edits."""

    def __init__(self, allowed_user_ids: set, allowed_role_ids: Optional[set], *, timeout):
        super().__init__(timeout=timeout)
        self._discord_module = discord
        self.allowed_user_ids = allowed_user_ids
        self.allowed_role_ids = allowed_role_ids or set()
        self.resolved = False
        self._interaction_claimed = False
        self._message = None

    def _check_auth(self, interaction: discord.Interaction) -> bool:
        from ..adapter import _component_check_auth
        return _component_check_auth(interaction, self.allowed_user_ids, self.allowed_role_ids)

    def add_item(self, item):
        """Place interactive V2 controls in ActionRows, as required by Discord."""
        if isinstance(self, getattr(discord.ui, "LayoutView", ())):
            button = getattr(discord.ui, "Button", ())
            select = getattr(discord.ui, "Select", ())
            if isinstance(item, (button, select)):
                row = discord.ui.ActionRow()
                row.add_item(item)
                return super().add_item(row)
        return super().add_item(item)

    def remove_item(self, item):
        """Remove a control whether it is direct or wrapped in an ActionRow."""
        if item in self.children:
            super().remove_item(item)
            return True
        for row in list(self.children):
            if hasattr(row, "remove_item"):
                try:
                    if item in getattr(row, "children", ()):
                        row.remove_item(item)
                        if not row.children:
                            super().remove_item(row)
                        return True
                except Exception:
                    continue
        return False

    async def _gate(self, interaction: discord.Interaction, *, resolved_msg: Optional[str], unauth_msg: str) -> bool:
        """Reject (ephemerally) an already-resolved or unauthorized click; True when it may proceed."""
        if resolved_msg is not None and (self.resolved or self._interaction_claimed):
            await interaction.response.send_message(resolved_msg, ephemeral=True)
            return False
        if not self._check_auth(interaction):
            await interaction.response.send_message(unauth_msg, ephemeral=True)
            return False
        # Claim before awaiting any resolver/edit so concurrent clicks cannot
        # resolve the same backend request twice. ``Other`` keeps this claim
        # while the gateway waits for the subsequent typed response.
        self._interaction_claimed = True
        return True

    def _disable_all(self) -> None:
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
            for nested in getattr(child, "children", ()):
                if hasattr(nested, "disabled"):
                    nested.disabled = True

    def _clear_controls(self) -> None:
        """Remove interactive controls without dropping the V2 text display."""
        text_display = getattr(self, "_v2_text_display", None)
        self.clear_items()
        if text_display is not None:
            self._children.insert(0, text_display)
            text_display._view = self
            if hasattr(self, "_total_children"):
                self._total_children = 1

    def _set_v2_text(self, text: str) -> bool:
        """Update the V2 text display while retaining legacy-view compatibility."""
        return update_text_display(self, text)

    async def _edit_prompt(self, interaction, *, embed=None, view=...):
        """Edit either a V2 text display or the legacy embed payload."""
        selected_view = self if view is ... else view
        if embed is not None and self._set_v2_text(text_from_payload({"embed": embed})):
            await interaction.response.edit_message(view=self)
            return
        await interaction.response.edit_message(embed=embed, view=selected_view)

    @staticmethod
    def _first_embed(message):
        return message.embeds[0] if message.embeds else None

    async def _expire_embed(self, footer: str) -> None:
        """Grey out the original message's embed after a timeout (best effort)."""
        msg = self._message
        if msg:
            try:
                if self._set_v2_text(footer):
                    await msg.edit(view=self)
                    return
                embed = self._first_embed(msg)
                if embed:
                    embed.color = discord.Color.greyple()
                    embed.set_footer(text=footer)
                await msg.edit(embed=embed, view=self)
            except Exception:
                pass  # message deleted or too old to edit

    async def _finalize_embed(self, interaction: discord.Interaction, color, footer: str) -> None:
        """Mark resolved, stamp the embed (color + footer), disable buttons, edit in place."""
        self.resolved = True
        embed = self._first_embed(interaction.message)
        if embed:
            embed.color = color
            embed.set_footer(text=footer)
        self._disable_all()
        if self._set_v2_text(footer):
            await interaction.response.edit_message(view=self)
            return
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        self.resolved = True
        self._disable_all()
        await self._expire_embed("⏱ Prompt expired — no action taken")
