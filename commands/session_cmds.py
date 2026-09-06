"""Commandes relatives aux sessions et conversations (/close, /reset, /status, /context, /sessions)."""

from __future__ import annotations

import logging
from typing import Any

import discord
from discord import app_commands
from views import SessionManagerView

logger = logging.getLogger(__name__)


def register_session_commands(tree: app_commands.CommandTree, adapter: Any) -> None:
    """Enregistre les commandes liées aux sessions."""

    @tree.command(name="close", description="Clôture et archive la session courante du fil de forum")
    async def cmd_close(interaction: discord.Interaction):
        if not adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Accès non autorisé.", ephemeral=True)
            return

        channel = interaction.channel
        if isinstance(channel, discord.Thread):
            await interaction.response.send_message(" Session clôturée. Archivage du fil en cours...", ephemeral=False)
            try:
                await channel.edit(archived=True, reason="Clôture demandée via /close")
            except Exception as e:
                logger.warning("[discord.commands] Échec archivage thread : %s", e)
        else:
            await interaction.response.send_message("ℹ️ `/close` s'applique uniquement dans un fil de forum.", ephemeral=True)

        await adapter.dispatch_command_action(
            command="close",
            args="",
            chat_id=str(interaction.channel_id),
            user_id=str(interaction.user.id),
            user_name=interaction.user.display_name,
        )

    @tree.command(name="reset", description="Réinitialise la session et l'historique de conversation")
    async def cmd_reset(interaction: discord.Interaction):
        if not adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Accès non autorisé.", ephemeral=True)
            return

        await interaction.response.send_message(" **Session réinitialisée avec succès.**", ephemeral=False)
        await adapter.dispatch_command_action(
            command="reset",
            args="",
            chat_id=str(interaction.channel_id),
            user_id=str(interaction.user.id),
            user_name=interaction.user.display_name,
        )

    @tree.command(name="status", description="Affiche le statut de la session active")
    async def cmd_status(interaction: discord.Interaction):
        if not adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Accès non autorisé.", ephemeral=True)
            return

        await interaction.response.send_message(" *Récupération du statut en cours...*", ephemeral=False)
        await adapter.dispatch_command_action(
            command="status",
            args="",
            chat_id=str(interaction.channel_id),
            user_id=str(interaction.user.id),
            user_name=interaction.user.display_name,
        )

    @tree.command(name="context", description="Analyse la saturation de la fenêtre de contexte et les tokens utilisés")
    async def cmd_context(interaction: discord.Interaction):
        if not adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Accès non autorisé.", ephemeral=True)
            return

        await interaction.response.send_message(" *Analyse du contexte de la session en cours...*", ephemeral=False)
        await adapter.dispatch_command_action(
            command="context",
            args="",
            chat_id=str(interaction.channel_id),
            user_id=str(interaction.user.id),
            user_name=interaction.user.display_name,
        )

    @tree.command(name="sessions", description="Gestionnaire interactif des sessions de forum")
    async def cmd_sessions(interaction: discord.Interaction):
        if not adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Accès non autorisé.", ephemeral=True)
            return

        threads = await adapter.fetch_forum_threads()
        view = SessionManagerView(adapter, threads)
        await interaction.response.send_message(embed=view.build_list_embed(), view=view, ephemeral=True)
