"""Vue des boutons d'actions post-réponse."""

from __future__ import annotations

import logging
from typing import Any, Optional

import discord
from discord.ui import Button, View

logger = logging.getLogger(__name__)

class PostResponseActionView(View):
    """Boutons affichés sous la réponse finale de l'agent dans les salons/threads."""

    def __init__(self, adapter: Any, chat_id: str, timeout: Optional[float] = 86400):
        super().__init__(timeout=timeout)
        self.adapter = adapter
        self.chat_id = str(chat_id)

    @discord.ui.button(label="Régénérer", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def regenerate_button(self, interaction: discord.Interaction, button: Button):
        if not self.adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Accès non autorisé.", ephemeral=True)
            return

        await interaction.response.send_message("🔄 Régénération de la réponse demandée...", ephemeral=True)
        await self.adapter.dispatch_button_action(
            action="regenerate",
            chat_id=self.chat_id,
            user_id=str(interaction.user.id),
            user_name=interaction.user.display_name,
            interaction_message=interaction.message,
        )

    @discord.ui.button(label="Clôturer", style=discord.ButtonStyle.secondary, emoji="🔒")
    async def close_button(self, interaction: discord.Interaction, button: Button):
        if not self.adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Accès non autorisé.", ephemeral=True)
            return

        channel = interaction.channel
        if isinstance(channel, discord.Thread):
            await interaction.response.send_message("🔒 Clôture et archivage de la session...", ephemeral=False)
            try:
                await channel.edit(archived=True, reason="Session clôturée via bouton Discord")
            except Exception as e:
                logger.warning("Échec archivage thread : %s", e)
        else:
            await interaction.response.send_message("Session fermée.", ephemeral=True)

        await self.adapter.dispatch_button_action(
            action="close",
            chat_id=self.chat_id,
            user_id=str(interaction.user.id),
            user_name=interaction.user.display_name,
            interaction_message=interaction.message,
        )
