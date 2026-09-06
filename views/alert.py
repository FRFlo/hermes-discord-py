"""Vue pour les alertes système en DM privé."""

from __future__ import annotations

import logging
from typing import Any, Optional

import discord
from discord.ui import Button, View

logger = logging.getLogger(__name__)


class SystemAlertView(View):
    """Boutons sous l'Embed d'alerte critique en DM privé."""

    def __init__(self, adapter: Any, task_id: str, timeout: Optional[float] = 86400):
        super().__init__(timeout=timeout)
        self.adapter = adapter
        self.task_id = task_id

    @discord.ui.button(label="Relancer la tâche", style=discord.ButtonStyle.primary, emoji="🔄")
    async def retry_button(self, interaction: discord.Interaction, button: Button):
        if not self.adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Non autorisé.", ephemeral=True)
            return
        await interaction.response.send_message("🔄 Relance de la tâche demandée...", ephemeral=True)
        await self.adapter.dispatch_button_action(
            action="retry_task",
            chat_id=str(interaction.channel_id),
            user_id=str(interaction.user.id),
            user_name=interaction.user.display_name,
            payload=self.task_id,
        )

    @discord.ui.button(label="Voir les logs", style=discord.ButtonStyle.secondary, emoji="📋")
    async def logs_button(self, interaction: discord.Interaction, button: Button):
        if not self.adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Non autorisé.", ephemeral=True)
            return
        await interaction.response.send_message("📋 Récupération des logs en cours...", ephemeral=True)
        await self.adapter.dispatch_button_action(
            action="view_logs",
            chat_id=str(interaction.channel_id),
            user_id=str(interaction.user.id),
            user_name=interaction.user.display_name,
            payload=self.task_id,
        )


