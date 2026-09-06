"""Vue de progression d'exécution des outils."""

from __future__ import annotations

import logging
from typing import Any, Optional

import discord
from discord.ui import Button, View

logger = logging.getLogger(__name__)

class ToolProgressView(View):
    """Bouton d'interruption immédiate affiché pendant l'exécution d'un outil."""

    def __init__(self, adapter: Any, chat_id: str, timeout: Optional[float] = 600):
        super().__init__(timeout=timeout)
        self.adapter = adapter
        self.chat_id = str(chat_id)

    @discord.ui.button(label="Interrompre", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def stop_button(self, interaction: discord.Interaction, button: Button):
        if not self.adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Accès non autorisé.", ephemeral=True)
            return

        await interaction.response.send_message(
            "⏹️ Signal d'interruption immédiat transmis à l'agent.", ephemeral=True
        )
        await self.adapter.cancel_active_progress(self.chat_id)
        await self.adapter.dispatch_command_action(
            command="stop",
            args="",
            chat_id=self.chat_id,
            user_id=str(interaction.user.id),
            user_name=interaction.user.display_name,
        )
