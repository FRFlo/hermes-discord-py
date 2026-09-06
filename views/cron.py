"""Gestionnaire et vues interactives pour les tâches Cron (/cron)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import discord
from discord import Embed, TextStyle
from discord.ui import Button, Modal, Select, TextInput, View

from .common import truncate

logger = logging.getLogger(__name__)

# =============================================================================

class CronCreateModal(Modal, title="Planifier une nouvelle tâche Cron"):
    name = TextInput(label="Nom de la tâche", placeholder="ex: Veille Matinale, Rapport Git...", required=True)
    schedule = TextInput(label="Fréquence / Expression Cron", placeholder="ex: 0 9 * * 1-5, every 2h...", required=True)
    prompt = TextInput(label="Instructions / Prompt", style=TextStyle.paragraph, placeholder="Consigne détaillée exécutée par l'agent...", required=True)
    deliver = TextInput(label="Salon de livraison (optionnel)", placeholder="Identifiant de salon ou 'dm' (vide = salon actuel)", required=False)

    def __init__(self, adapter: Any, chat_id: str):
        super().__init__()
        self.adapter = adapter
        self.chat_id = chat_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"⏳ Création de la tâche cron **{self.name.value}** en cours...", ephemeral=True
        )
        await self.adapter.handle_cron_create(
            name=self.name.value.strip(),
            schedule=self.schedule.value.strip(),
            prompt=self.prompt.value.strip(),
            deliver=self.deliver.value.strip() or self.chat_id,
            chat_id=self.chat_id,
        )


class CronSelect(Select):
    def __init__(self, view: CronManagerView, jobs: List[Dict[str, Any]]):
        self.cron_view = view
        opts = []
        for j in jobs[:25]:
            icon = "🟢" if j.get("enabled", True) else "⏸️"
            lbl = truncate(j.get("name") or j.get("id", "Job"), 100)
            sched = truncate(j.get("schedule_display") or j.get("schedule", ""), 100)
            opts.append(
                discord.SelectOption(
                    label=f"{icon} {lbl}",
                    value=str(j.get("id")),
                    description=sched,
                )
            )
        super().__init__(placeholder="Inspecter une tâche cron...", min_values=1, max_values=1, options=opts)

    async def callback(self, interaction: discord.Interaction):
        job_id = self.values[0]
        await self.cron_view.show_job_detail(interaction, job_id)


class CronManagerView(View):
    """Vue interactive pour la commande /cron."""

    def __init__(self, adapter: Any, chat_id: str, jobs: List[Dict[str, Any]]):
        super().__init__(timeout=300.0)
        self.adapter = adapter
        self.chat_id = chat_id
        self.jobs = jobs
        self.selected_job_id: Optional[str] = None

        if jobs:
            self.add_item(CronSelect(self, jobs))

    def build_list_embed(self) -> Embed:
        embed = Embed(
            title="⏰ Gestionnaire des Tâches Cron Hermes",
            color=0x5865F2,
            description=(
                "Consultez et pilotez vos tâches planifiées ci-dessous.\n"
                "Sélectionnez une tâche dans le menu pour l'inspecter, ou cliquez sur **➕ Planifier**.\n\n"
            ),
        )
        if not self.jobs:
            embed.description += "*Aucune tâche cron configurée pour le moment.*"
        else:
            for idx, j in enumerate(self.jobs[:10]):
                icon = "🟢" if j.get("enabled", True) else "⏸️"
                sched = j.get("schedule_display") or j.get("schedule", "")
                embed.add_field(
                    name=f"{idx + 1}. {icon} {truncate(j.get('name') or j.get('id'), 40)}",
                    value=f"↳ Fréquence : `{sched}`",
                    inline=False,
                )
        return embed

    def build_detail_embed(self, job: Dict[str, Any]) -> Embed:
        is_enabled = job.get("enabled", True)
        embed = Embed(
            title=f"{'🟢' if is_enabled else '⏸️'} Tâche : {job.get('name') or job.get('id')}",
            color=0x57F287 if is_enabled else 0xFEE75C,
        )
        embed.add_field(name="Identifiant", value=f"`{job.get('id')}`", inline=True)
        embed.add_field(name="Statut", value="Actif" if is_enabled else "En pause", inline=True)
        embed.add_field(name="Fréquence", value=f"`{job.get('schedule_display') or job.get('schedule')}`", inline=True)
        if job.get("prompt"):
            embed.add_field(name="Prompt", value=f"```\n{truncate(job['prompt'], 800)}\n```", inline=False)
        return embed

    async def show_job_detail(self, interaction: discord.Interaction, job_id: str):
        self.selected_job_id = job_id
        job = next((j for j in self.jobs if str(j.get("id")) == job_id), None)
        if not job:
            await interaction.response.send_message("❌ Tâche introuvable.", ephemeral=True)
            return

        detail_view = CronDetailView(self.adapter, self.chat_id, job, self)
        await interaction.response.edit_message(embed=self.build_detail_embed(job), view=detail_view)

    @discord.ui.button(label="Planifier une tâche", style=discord.ButtonStyle.success, emoji="➕")
    async def create_button(self, interaction: discord.Interaction, button: Button):
        if not self.adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Non autorisé.", ephemeral=True)
            return
        await interaction.response.send_modal(CronCreateModal(self.adapter, self.chat_id))

    @discord.ui.button(label="Rafraîchir", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def refresh_button(self, interaction: discord.Interaction, button: Button):
        self.jobs = self.adapter.fetch_cron_jobs()
        self.clear_items()
        if self.jobs:
            self.add_item(CronSelect(self, self.jobs))
        self.add_item(self.create_button)
        self.add_item(self.refresh_button)
        await interaction.response.edit_message(embed=self.build_list_embed(), view=self)


class CronDetailView(View):
    """Boutons de contrôle pour une tâche cron spécifique."""

    def __init__(self, adapter: Any, chat_id: str, job: Dict[str, Any], parent_view: CronManagerView):
        super().__init__(timeout=300.0)
        self.adapter = adapter
        self.chat_id = chat_id
        self.job = job
        self.parent_view = parent_view
        self.job_id = str(job.get("id"))

        is_enabled = job.get("enabled", True)
        if is_enabled:
            self.pause_btn = Button(label="Mettre en pause", style=discord.ButtonStyle.secondary, emoji="⏸️")
            self.pause_btn.callback = self._pause_callback
            self.add_item(self.pause_btn)
        else:
            self.resume_btn = Button(label="Reprendre", style=discord.ButtonStyle.success, emoji="▶️")
            self.resume_btn.callback = self._resume_callback
            self.add_item(self.resume_btn)

    async def _pause_callback(self, interaction: discord.Interaction):
        await self.adapter.handle_cron_action("pause", self.job_id, self.chat_id)
        await interaction.response.send_message(f"⏸️ Tâche `{self.job_id}` mise en pause.", ephemeral=True)

    async def _resume_callback(self, interaction: discord.Interaction):
        await self.adapter.handle_cron_action("resume", self.job_id, self.chat_id)
        await interaction.response.send_message(f"▶️ Tâche `{self.job_id}` reprise.", ephemeral=True)

    @discord.ui.button(label="Exécuter maintenant", style=discord.ButtonStyle.primary, emoji="⚡")
    async def run_button(self, interaction: discord.Interaction, button: Button):
        await self.adapter.handle_cron_action("trigger", self.job_id, self.chat_id)
        await interaction.response.send_message(f"⚡ Exécution immédiate lancée pour `{self.job_id}`.", ephemeral=True)

    @discord.ui.button(label="Dernier output", style=discord.ButtonStyle.secondary, emoji="📋")
    async def output_button(self, interaction: discord.Interaction, button: Button):
        output = self.adapter.get_cron_last_output(self.job_id)
        if output:
            msg = f"📋 **Dernier rapport d'exécution pour `{self.job_id}` :**\n```markdown\n{output[:1800]}\n```"
        else:
            msg = f"ℹ️ Aucun rapport d'exécution disponible pour `{self.job_id}`."
        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(label="Supprimer", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_button(self, interaction: discord.Interaction, button: Button):
        await self.adapter.handle_cron_action("delete", self.job_id, self.chat_id)
        await interaction.response.send_message(f"🗑️ Tâche `{self.job_id}` supprimée.", ephemeral=True)

    @discord.ui.button(label="Retour à la liste", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def back_button(self, interaction: discord.Interaction, button: Button):
        self.parent_view.jobs = self.adapter.fetch_cron_jobs()
        await interaction.response.edit_message(embed=self.parent_view.build_list_embed(), view=self.parent_view)
