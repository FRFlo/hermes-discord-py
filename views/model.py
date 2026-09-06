"""Sélecteur interactif et gestion des modèles LLM (/model)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import discord
from discord import Embed
from discord.ui import Button, Modal, Select, TextInput, View

logger = logging.getLogger(__name__)

AVAILABLE_MODELS: List[Dict[str, str]] = [
    {"label": "Gemini Pro Agent (Défaut)", "value": "gemini-pro-agent", "description": "Modèle principal configuré via cliproxyapi"},
    {"label": "Gemini 2.5 Pro", "value": "gemini-2.5-pro", "description": "Raisonnement approfondi et immense fenêtre de contexte"},
    {"label": "Gemini 2.5 Flash", "value": "gemini-2.5-flash", "description": "Ultra rapide et économique"},
    {"label": "Claude 3.5 Sonnet", "value": "claude-3-5-sonnet", "description": "Excellence en programmation et architecture"},
    {"label": "GPT-4o", "value": "gpt-4o", "description": "Modèle polyvalent et multimodal d'OpenAI"},
    {"label": "DeepSeek Chat", "value": "deepseek-chat", "description": "Haute performance et coût minimal"},
    {"label": "o3-mini", "value": "o3-mini", "description": "Raisonnement logique et mathématique"},
]

class ModelCustomModal(Modal, title="Saisir un modèle personnalisé"):
    model_name = TextInput(
        label="Identifiant du modèle",
        placeholder="ex: anthropic/claude-3-7-sonnet, openai/o3-mini...",
        required=True,
    )

    def __init__(self, adapter: Any, chat_id: str):
        super().__init__()
        self.adapter = adapter
        self.chat_id = chat_id

    async def on_submit(self, interaction: discord.Interaction):
        val = self.model_name.value.strip()
        embed = Embed(
            title="🤖 Modèle LLM Personnalisé",
            description=f"Le modèle de cette session a été configuré sur : **`{val}`**.",
            color=0x57F287,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await self.adapter.dispatch_command_action(
            command="model",
            args=val,
            chat_id=self.chat_id,
            user_id=str(interaction.user.id),
            user_name=interaction.user.display_name,
        )


class ModelSelect(Select):
    def __init__(self, adapter: Any, chat_id: str):
        self.adapter = adapter
        self.chat_id = chat_id
        opts = [
            discord.SelectOption(
                label=m["label"],
                value=m["value"],
                description=m["description"],
                emoji="🤖",
            )
            for m in AVAILABLE_MODELS
        ]
        super().__init__(placeholder="Choisissez un modèle LLM...", min_values=1, max_values=1, options=opts)

    async def callback(self, interaction: discord.Interaction):
        if not self.adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Non autorisé.", ephemeral=True)
            return

        selected = self.values[0]
        embed = Embed(
            title="🤖 Modèle LLM Modifié",
            description=f"Le modèle de cette session a été configuré sur : **`{selected}`**.",
            color=0x57F287,
        )
        await interaction.response.edit_message(embed=embed, view=None)
        await self.adapter.dispatch_command_action(
            command="model",
            args=selected,
            chat_id=self.chat_id,
            user_id=str(interaction.user.id),
            user_name=interaction.user.display_name,
        )


class ModelSelectView(View):
    """Vue interactive pour la commande /model."""

    def __init__(self, adapter: Any, chat_id: str):
        super().__init__(timeout=180.0)
        self.adapter = adapter
        self.chat_id = chat_id
        self.add_item(ModelSelect(adapter, chat_id))

    @discord.ui.button(label="Saisir un autre modèle", style=discord.ButtonStyle.primary, emoji="✏️")
    async def custom_button(self, interaction: discord.Interaction, button: Button):
        if not self.adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Non autorisé.", ephemeral=True)
            return
        await interaction.response.send_modal(ModelCustomModal(self.adapter, self.chat_id))

    @discord.ui.button(label="Défaut (gemini-pro-agent)", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def default_button(self, interaction: discord.Interaction, button: Button):
        if not self.adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Non autorisé.", ephemeral=True)
            return
        embed = Embed(
            title="🤖 Modèle LLM Réinitialisé",
            description="Le modèle a été réinitialisé sur la valeur par défaut : **`gemini-pro-agent`**.",
            color=0x57F287,
        )
        await interaction.response.edit_message(embed=embed, view=None)
        await self.adapter.dispatch_command_action(
            command="model",
            args="gemini-pro-agent",
            chat_id=self.chat_id,
            user_id=str(interaction.user.id),
            user_name=interaction.user.display_name,
        )

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def dismiss_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Sélecteur fermé.", embed=None, view=None)
