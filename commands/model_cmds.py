"""Commandes de sélection et configuration du modèle LLM (/model)."""

from __future__ import annotations

import logging
from typing import Any, List, Optional

import discord
from discord import app_commands
from ..views import AVAILABLE_MODELS, ModelSelectView

logger = logging.getLogger(__name__)


def register_model_commands(tree: app_commands.CommandTree, adapter: Any) -> None:
    """Enregistre la commande /model et son autocomplétion."""

    @tree.command(name="model", description="Consulte ou modifie le modèle LLM actif pour cette session")
    @app_commands.describe(name="Identifiant du modèle (laisser vide pour ouvrir le sélecteur interactif)")
    async def cmd_model(interaction: discord.Interaction, name: Optional[str] = None):
        if not adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Accès non autorisé.", ephemeral=True)
            return

        chat_id = str(interaction.channel_id)
        if name:
            await interaction.response.send_message(f" **Bascule demandée vers le modèle :** `{name}`...", ephemeral=False)
            await adapter.dispatch_command_action(
                command="model",
                args=name,
                chat_id=chat_id,
                user_id=str(interaction.user.id),
                user_name=interaction.user.display_name,
            )
            return

        embed = discord.Embed(
            title=" Gestionnaire & Sélecteur de Modèle LLM",
            color=0x5865F2,
            description=(
                "Choisissez un modèle parmi la liste optimisée ci-dessous, "
                "ou cliquez sur **Saisir un autre modèle** pour spécifier n'importe quel identifiant."
            ),
        )
        embed.add_field(name="⭐ Recommandé", value="`gemini-pro-agent` (cliproxyapi)", inline=True)
        embed.add_field(name="⚡ Bascule rapide", value="Sélectionnez dans le menu", inline=True)
        embed.set_footer(text="La modification s'applique immédiatement à cette session")

        view = ModelSelectView(adapter, chat_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @cmd_model.autocomplete("name")
    async def cmd_model_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        query = current.lower()
        filtered = [
            m for m in AVAILABLE_MODELS
            if query in m["value"].lower() or query in m["label"].lower()
        ][:25]
        return [
            app_commands.Choice(name=f"{m['label']} ({m['value']})"[:100], value=m["value"])
            for m in filtered
        ]
