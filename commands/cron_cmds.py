"""Commandes de gestion des tâches Cron Hermes (/cron)."""

from __future__ import annotations

import logging
from typing import Any

import discord
from discord import app_commands
from views import CronManagerView

logger = logging.getLogger(__name__)


def register_cron_commands(tree: app_commands.CommandTree, adapter: Any) -> None:
    """Enregistre la commande /cron."""

    @tree.command(name="cron", description="Gestionnaire interactif des tâches planifiées Cron Hermes")
    async def cmd_cron(interaction: discord.Interaction):
        if not adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Accès non autorisé.", ephemeral=True)
            return

        jobs = adapter.fetch_cron_jobs()
        view = CronManagerView(adapter, str(interaction.channel_id), jobs)
        await interaction.response.send_message(embed=view.build_list_embed(), view=view, ephemeral=True)
