"""Vue d'approbation d'exécution de commande sensible."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord
from discord.ui import Button, View

logger = logging.getLogger(__name__)

class ApprovalView(View):
    """Boutons interactifs d'approbation ou de rejet d'une commande sensible."""

    def __init__(self, adapter: Any, chat_id: str, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.adapter = adapter
        self.chat_id = str(chat_id)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        self.future: asyncio.Future[bool] = loop.create_future()

    @discord.ui.button(label="Approuver", style=discord.ButtonStyle.success, emoji="✅")
    async def approve_button(self, interaction: discord.Interaction, button: Button):
        if not self.adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Non autorisé.", ephemeral=True)
            return

        for item in self.children:
            item.disabled = True  # type: ignore
        await interaction.response.edit_message(content="✅ **Commande approuvée.**", view=self)
        if not self.future.done():
            self.future.set_result(True)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger, emoji="❌")
    async def deny_button(self, interaction: discord.Interaction, button: Button):
        if not self.adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Non autorisé.", ephemeral=True)
            return

        for item in self.children:
            item.disabled = True  # type: ignore
        await interaction.response.edit_message(content="❌ **Commande refusée.**", view=self)
        if not self.future.done():
            self.future.set_result(False)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore
        if not self.future.done():
            self.future.set_result(False)

