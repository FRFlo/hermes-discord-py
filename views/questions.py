"""Questions interactives et clarifications style pi-bridge."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Any, Dict, List, Optional

import discord
from discord import Embed, TextStyle
from discord.ui import Button, Modal, Select, TextInput, View

from .common import truncate

logger = logging.getLogger(__name__)

class QuestionTextModal(Modal, title="Saisie de réponse personnalisée"):
    """Modale Discord permettant la saisie d'un texte libre pour une question interactive."""

    custom_text = TextInput(
        label="Votre réponse",
        style=TextStyle.paragraph,
        placeholder="Précisez votre demande ou vos instructions...",
        required=True,
        max_length=2000,
    )

    def __init__(self, view: QuestionInteractiveView):
        super().__init__()
        self.question_view = view

    async def on_submit(self, interaction: discord.Interaction):
        await self.question_view.handle_custom_text(interaction, self.custom_text.value.strip())


class QuestionOptionSelect(Select):
    """Menu déroulant des options pour les questions interactives."""

    def __init__(self, view: QuestionInteractiveView, options: List[Dict[str, Any]], multi_select: bool):
        self.question_view = view
        max_vals = min(len(options), 25) if multi_select else 1
        select_options = []
        for i, opt in enumerate(options[:25]):
            label = truncate(opt.get("label", f"Option {i + 1}"), 100)
            val = str(opt.get("value", label))
            desc = truncate(opt.get("description", ""), 100) or None
            select_options.append(discord.SelectOption(label=label, value=val, description=desc))

        super().__init__(
            placeholder="Sélectionnez une ou plusieurs options...",
            min_values=1,
            max_values=max_vals,
            options=select_options,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.question_view.handle_select(interaction, self.values)


class QuestionInteractiveView(View):
    """Vue interactive complète pour ask_question et send_clarify (style pi-bridge)."""

    def __init__(
        self,
        adapter: Any,
        chat_id: str,
        question: str,
        options: Optional[List[Dict[str, Any]]] = None,
        details: Optional[str] = None,
        context: Optional[str] = None,
        multi_select: bool = False,
        timeout_seconds: Optional[int] = None,
        clarify_id: Optional[str] = None,
    ):
        super().__init__(timeout=float(timeout_seconds) if timeout_seconds else 600.0)
        self.adapter = adapter
        self.chat_id = str(chat_id)
        self.question = question
        self.raw_options = options or []
        self.details = details
        self.context = context
        self.multi_select = multi_select
        self.clarify_id = clarify_id
        self.selected_values: List[str] = []
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        self.future: asyncio.Future[Dict[str, Any]] = loop.create_future()
        self.message: Optional[discord.Message] = None

        if self.raw_options:
            self.add_item(QuestionOptionSelect(self, self.raw_options, multi_select))

        # Bouton Autre (texte libre)
        other_btn = Button(label="Autre (texte)", style=discord.ButtonStyle.primary, emoji="✏️")
        other_btn.callback = self._open_modal_callback
        self.add_item(other_btn)

        # Bouton Valider si multi-select
        if multi_select:
            val_btn = Button(label="Valider la sélection", style=discord.ButtonStyle.success, emoji="✅")
            val_btn.callback = self._validate_multi_callback
            self.add_item(val_btn)

        # Bouton Annuler
        cancel_btn = Button(label="Annuler", style=discord.ButtonStyle.secondary, emoji="❌")
        cancel_btn.callback = self._cancel_callback
        self.add_item(cancel_btn)

    def build_main_embed(self) -> Embed:
        """Construit l'Embed initial pour la question."""
        embed = Embed(
            title="❓ Question & Précision Requise",
            description=f"### {self.question}",
            color=0x5865F2,  # Discord Blurple
        )
        if self.details:
            embed.add_field(name="ℹ️ Détails", value=truncate(self.details, 1024), inline=False)
        if self.context:
            embed.add_field(name="📋 Contexte", value=f"```\n{truncate(self.context, 1000)}\n```", inline=False)

        if self.raw_options:
            opt_lines = []
            for i, opt in enumerate(self.raw_options[:25]):
                lbl = opt.get("label", f"Option {i + 1}")
                desc = f" — *{opt['description']}*" if opt.get("description") else ""
                opt_lines.append(f"**{i + 1}.** {lbl}{desc}")
            embed.add_field(name="Choix possibles", value="\n".join(opt_lines[:15]), inline=False)

        if self.timeout:
            expire_ts = int(dt.datetime.now().timestamp() + self.timeout)
            embed.set_footer(text=f"Expire dans {int(self.timeout)}s")
            embed.description += f"\n\n⏱️ *Expiration : <t:{expire_ts}:R>*"

        return embed

    async def _open_modal_callback(self, interaction: discord.Interaction):
        if not self.adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Non autorisé.", ephemeral=True)
            return
        await interaction.response.send_modal(QuestionTextModal(self))

    async def _validate_multi_callback(self, interaction: discord.Interaction):
        if not self.adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Non autorisé.", ephemeral=True)
            return
        if not self.selected_values:
            await interaction.response.send_message("⚠️ Veuillez d'abord faire un choix dans le menu.", ephemeral=True)
            return
        await self._finalize_resolution(interaction, self.selected_values)

    async def _cancel_callback(self, interaction: discord.Interaction):
        if not self.adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Non autorisé.", ephemeral=True)
            return
        for item in self.children:
            item.disabled = True  # type: ignore
        embed = Embed(
            title="❌ Question Annulée",
            description=f"La question a été annulée par {interaction.user.mention}.",
            color=0xED4245,  # Discord Red
        )
        await interaction.response.edit_message(embed=embed, view=self)
        if not self.future.done():
            self.future.set_result({"status": "cancelled", "answers": []})

    async def handle_select(self, interaction: discord.Interaction, values: List[str]):
        if not self.adapter.is_user_authorized(interaction.user.id):
            await interaction.response.send_message("⛔ Non autorisé.", ephemeral=True)
            return

        self.selected_values = values
        if not self.multi_select:
            # En single-select, la sélection valide immédiatement
            await self._finalize_resolution(interaction, values)
        else:
            await interaction.response.send_message(
                f"Sélection actuelle : {', '.join(values)}. Cliquez sur **Valider la sélection** pour confirmer.",
                ephemeral=True,
            )

    async def handle_custom_text(self, interaction: discord.Interaction, text: str):
        await self._finalize_resolution(interaction, [text])

    async def _finalize_resolution(self, interaction: discord.Interaction, answers: List[str]):
        for item in self.children:
            item.disabled = True  # type: ignore

        embed = Embed(
            title="✅ Choix Validé",
            description=f"**Réponse enregistrée :**\n" + "\n".join(f"• {a}" for a in answers),
            color=0x57F287,  # Discord Green
        )
        embed.set_footer(text=f"Validé par {interaction.user.display_name}")

        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=None)
            elif self.message:
                await self.message.edit(embed=embed, view=None)
        except Exception as e:
            logger.debug("Échec mise à jour affichage question : %s", e)

        if not self.future.done():
            self.future.set_result({"status": "resolved", "answers": answers})

        if self.clarify_id:
            try:
                from tools.clarify_gateway import resolve_gateway_clarify
                ans_str = ", ".join(answers) if len(answers) > 1 else (answers[0] if answers else "")
                resolve_gateway_clarify(self.clarify_id, ans_str)
            except Exception as e:
                logger.debug("Échec resolve_gateway_clarify pour %s : %s", self.clarify_id, e)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore
        if self.message:
            try:
                embed = Embed(
                    title="⏰ Question Expirée",
                    description="Le temps alloué pour répondre à cette question s'est écoulé.",
                    color=0xED4245,
                )
                await self.message.edit(embed=embed, view=None)
            except Exception:
                pass
        if not self.future.done():
            self.future.set_result({"status": "timeout", "answers": []})
