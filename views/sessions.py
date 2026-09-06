"""Gestionnaire et vues interactives pour les sessions de forum (/sessions)."""

from __future__ import annotations

import logging
from typing import Any, List

import discord
from discord import Embed
from discord.ui import Button, Modal, Select, TextInput, View

from .common import truncate

logger = logging.getLogger(__name__)

# =============================================================================

class SessionRenameModal(Modal, title="Renommer la session"):
    new_name = TextInput(label="Nouveau titre de la session", max_length=100, required=True)

    def __init__(self, adapter: Any, thread: discord.Thread):
        super().__init__()
        self.adapter = adapter
        self.thread = thread

    async def on_submit(self, interaction: discord.Interaction):
        name = self.new_name.value.strip()
        try:
            await self.thread.edit(name=name)
            await interaction.response.send_message(f"✏️ Fil renommé en **{name}** avec succès.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Échec renommage : {e}", ephemeral=True)


class SessionSelect(Select):
    def __init__(self, view: SessionManagerView, threads: List[discord.Thread]):
        self.session_view = view
        opts = []
        for t in threads[:25]:
            icon = "📁" if t.archived else "💬"
            opts.append(
                discord.SelectOption(
                    label=truncate(f"{icon} {t.name}", 100),
                    value=str(t.id),
                    description=f"{t.message_count or 0} messages",
                )
            )
        super().__init__(placeholder="Sélectionnez une session forum...", min_values=1, max_values=1, options=opts)

    async def callback(self, interaction: discord.Interaction):
        thread_id = int(self.values[0])
        thread = interaction.client.get_channel(thread_id)  # type: ignore
        if not thread:
            try:
                thread = await interaction.client.fetch_channel(thread_id)
            except Exception:
                thread = None

        if isinstance(thread, discord.Thread):
            await self.session_view.show_thread_detail(interaction, thread)
        else:
            await interaction.response.send_message("❌ Session introuvable.", ephemeral=True)


class SessionManagerView(View):
    """Vue interactive pour la commande /sessions."""

    def __init__(self, adapter: Any, threads: List[discord.Thread]):
        super().__init__(timeout=300.0)
        self.adapter = adapter
        self.threads = threads
        if threads:
            self.add_item(SessionSelect(self, threads))

    def build_list_embed(self) -> Embed:
        embed = Embed(
            title="📂 Gestionnaire des Sessions Forum Hermes",
            color=0x5865F2,
            description="Sélectionnez une session ci-dessous pour la renommer, l'archiver ou la supprimer.\n\n",
        )
        if not self.threads:
            embed.description += "*Aucun fil de session trouvé dans le forum.*"
        else:
            for idx, t in enumerate(self.threads[:10]):
                icon = "📦" if t.archived else "🟢"
                embed.add_field(
                    name=f"{idx + 1}. {icon} {truncate(t.name, 40)}",
                    value=f"Messages: {t.message_count or 0} — [Ouvrir le fil]({t.jump_url})",
                    inline=False,
                )
        return embed

    async def show_thread_detail(self, interaction: discord.Interaction, thread: discord.Thread):
        embed = Embed(
            title=f"{'📦' if thread.archived else '🟢'} Session : {thread.name}",
            color=0x57F287 if not thread.archived else 0x95A5A6,
        )
        embed.add_field(name="Identifiant", value=f"`{thread.id}`", inline=True)
        embed.add_field(name="Statut", value="Archivé" if thread.archived else "Actif", inline=True)
        embed.add_field(name="Messages", value=str(thread.message_count or 0), inline=True)
        embed.add_field(name="Lien direct", value=f"[Accéder au fil]({thread.jump_url})", inline=False)

        detail_view = SessionDetailView(self.adapter, thread, self)
        await interaction.response.edit_message(embed=embed, view=detail_view)


class SessionDetailView(View):
    """Boutons d'action pour une session forum spécifique."""

    def __init__(self, adapter: Any, thread: discord.Thread, parent_view: SessionManagerView):
        super().__init__(timeout=300.0)
        self.adapter = adapter
        self.thread = thread
        self.parent_view = parent_view

    @discord.ui.button(label="Renommer", style=discord.ButtonStyle.primary, emoji="✏️")
    async def rename_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(SessionRenameModal(self.adapter, self.thread))

    @discord.ui.button(label="Archiver / Désarchiver", style=discord.ButtonStyle.secondary, emoji="📦")
    async def toggle_archive_button(self, interaction: discord.Interaction, button: Button):
        new_state = not self.thread.archived
        try:
            await self.thread.edit(archived=new_state)
            action_text = "archivé" if new_state else "désarchivé"
            await interaction.response.send_message(f"Fil {action_text} avec succès.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Échec : {e}", ephemeral=True)

    @discord.ui.button(label="Supprimer", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_button(self, interaction: discord.Interaction, button: Button):
        thread_id = str(self.thread.id)
        try:
            await self.thread.delete()
            await self.adapter.purge_session(thread_id)
            await interaction.response.send_message(f"🗑️ Session `{thread_id}` supprimée de Discord et d'Hermes.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Échec suppression : {e}", ephemeral=True)

    @discord.ui.button(label="Retour à la liste", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def back_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(embed=self.parent_view.build_list_embed(), view=self.parent_view)
