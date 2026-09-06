"""Commandes de contrôle d'exécution (/stop)."""

from __future__ import annotations

import logging
from typing import Any

import discord
from discord import app_commands

logger = logging.getLogger(__name__)


def register_control_commands(tree: app_commands.CommandTree, adapter: Any) -> None:
    """Enregistre les commandes de contrôle."""

    @tree.command(name="stop", description="Interrompt immédiatement la commande ou tâche en cours")
    async def cmd_stop(interaction: discord.Interaction):
        if not adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Accès non autorisé.", ephemeral=True)
            return

        await interaction.response.send_message("⏹️ Signal d'interruption immédiat transmis à l'agent.", ephemeral=True)
        await adapter.cancel_active_progress(str(interaction.channel_id))
        await adapter.dispatch_command_action(
            command="stop",
            args="",
            chat_id=str(interaction.channel_id),
            user_id=str(interaction.user.id),
            user_name=interaction.user.display_name,
        )
