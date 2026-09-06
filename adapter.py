"""
Adaptateur de plateforme Discord natif pour Hermes Agent basé sur discord.py.

Fournit une intégration complète, performante et hautement modulaire :
- Architecture découpée en modules thématiques : views/, commands/, services/, events/.
- Gestion native des sessions de travail par salons / posts Forum Discord.
- Communications système, alertes critiques et rapports cron acheminés en DM.
- Découpage Markdown intelligent respectant la limite de 2 000 caractères et préservant les blocs de code.
- Formatage du raisonnement IA (Thinking) en sous-texte compact natif Discord (-#).
- Suivi dynamique de l'exécution des outils en direct avec repli automatique en spoiler (||...||).
- Sauvegarde et attachement automatique des sorties de commandes volumineuses (> 1 500 car.) en fichiers .log/.diff.
- Réactions émojis de statut et gestion de file d'attente intelligente (⏱️ -> ⏳ -> ✅ / ❌).
- Bouton rouge d'interruption immédiate (⏹️ Interrompre) et boutons d'actions sous la réponse ( Régénérer,  Clôturer).
- Système riche de questions et clarifications interactives (style pi-bridge : menus déroulants, modales de texte libre).
- Commandes slash natives Discord (/close, /stop, /reset, /status, /context, /model, /cron, /sessions).
- Support du cycle de vie avancé des messages (suppression et édition avec troncature et régénération).
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import discord
from discord import app_commands
from discord.ext import commands

try:
    from hermes_agent.gateway.config import Platform, PlatformConfig
    from hermes_agent.gateway.platforms.base import (
        BasePlatformAdapter,
        MessageEvent,
        MessageType,
        SendResult,
    )
except ImportError:
    import sys
    _HERMES_ROOT = Path("C:/Users/Flo/Desktop/hermes-agent")
    if str(_HERMES_ROOT) not in sys.path:
        sys.path.insert(0, str(_HERMES_ROOT))
    from gateway.config import Platform, PlatformConfig
    from gateway.platforms.base import (
        BasePlatformAdapter,
        MessageEvent,
        MessageType,
        SendResult,
    )

# Imports des modules thématiques locaux
try:
    from .commands import setup_all_commands
    from .downloader import download_and_cache_attachment
    from .events import handle_message_delete, handle_message_edit
    from .services import (
        fetch_cron_jobs,
        fetch_forum_threads,
        get_cron_last_output,
        handle_cron_action,
        handle_cron_create,
        load_session_transcript,
        purge_session,
        resolve_session_id,
        rewrite_session_transcript,
    )
    from .splitter import (
        format_thinking_with_subtext,
        save_large_output_to_log_file,
        split_markdown,
    )
    from .views import (
        AVAILABLE_MODELS,
        ApprovalView,
        CronManagerView,
        ModelSelectView,
        PostResponseActionView,
        QuestionInteractiveView,
        SessionManagerView,
        SystemAlertView,
        ToolProgressView,
    )
except ImportError:
    from .commands import setup_all_commands
    from .downloader import download_and_cache_attachment
    from .events import handle_message_delete, handle_message_edit
    from ..services import (
        fetch_cron_jobs,
        fetch_forum_threads,
        get_cron_last_output,
        handle_cron_action,
        handle_cron_create,
        load_session_transcript,
        purge_session,
        resolve_session_id,
        rewrite_session_transcript,
    )
    from splitter import (
        format_thinking_with_subtext,
        save_large_output_to_log_file,
        split_markdown,
    )
    from ..views import (
        AVAILABLE_MODELS,
        ApprovalView,
        CronManagerView,
        ModelSelectView,
        PostResponseActionView,
        QuestionInteractiveView,
        SessionManagerView,
        SystemAlertView,
        ToolProgressView,
    )

logger = logging.getLogger(__name__)

_DEFAULT_ALLOWED_USER = "544862774002581504"
_DEFAULT_FORUM_CHANNEL = "1544452203207589938"


def check_discord_requirements() -> bool:
    """Vérifie si la bibliothèque discord.py est disponible."""
    try:
        import discord
        return True
    except ImportError:
        return False


class DiscordPyAdapter(BasePlatformAdapter):
    """Adaptateur natif discord.py pour Hermes Agent."""

    def __init__(self, config: PlatformConfig):
        platform = Platform.DISCORD if hasattr(Platform, "DISCORD") else Platform("discord")
        super().__init__(config, platform)

        self._bot_token = (
            os.environ.get("DISCORD_BOT_TOKEN")
            or getattr(config, "bot_token", None)
            or ""
        ).strip()

        allowed_raw = os.environ.get("DISCORD_ALLOWED_USERS", _DEFAULT_ALLOWED_USER)
        self._allowed_users: Set[str] = {
            u.strip() for u in allowed_raw.split(",") if u.strip()
        }
        self._allow_all = (
            os.environ.get("DISCORD_ALLOW_ALL_USERS", "false").lower() == "true"
            or os.environ.get("GATEWAY_ALLOW_ALL_USERS", "false").lower() == "true"
        )

        self._forum_channel_id = os.environ.get("DISCORD_FORUM_CHANNEL_ID", _DEFAULT_FORUM_CHANNEL).strip()
        self._home_channel = os.environ.get("DISCORD_HOME_CHANNEL", "").strip()
        self._enable_reactions = os.environ.get("DISCORD_REACTIONS", "true").lower() != "false"
        self._uploads_dir = os.environ.get("HERMES_UPLOADS_DIR") or str(Path.cwd() / "uploads")

        # Correspondance des messages pour suppression et édition dynamique
        self._reply_map: Dict[str, List[str]] = {}  # user_msg_id -> [bot_msg_ids]
        self._bot_to_user_map: Dict[str, str] = {}  # bot_msg_id -> user_msg_id

        # Suivi de progression des outils par salon (live update + repli spoiler)
        self._active_progress: Dict[str, Dict[str, Any]] = {}

        # État d'occupation et file d'attente émojis
        self._busy_chats: Set[str] = set()

        # Configuration du client Discord avec les intents nécessaires
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        intents.guilds = True
        intents.dm_messages = True

        self._bot = commands.Bot(command_prefix="!", intents=intents)
        self._tree = self._bot.tree
        self._main_task: Optional[asyncio.Task] = None

        self._register_discord_events()
        self._setup_commands()

    # =========================================================================
    # Événements Discord
    # =========================================================================

    def _register_discord_events(self) -> None:
        """Enregistre les écouteurs d'événements du bot Discord."""

        @self._bot.event
        async def on_ready():
            logger.info("[discord] Bot connecté en tant que %s (ID: %s)", self._bot.user, self._bot.user.id if self._bot.user else "inconnu")
            try:
                synced = await self._tree.sync()
                logger.info("[discord] %d commandes slash synchronisées avec succès.", len(synced))
            except Exception as e:
                logger.warning("[discord] Erreur lors de la synchronisation des commandes slash : %s", e)

        @self._bot.event
        async def on_message(message: discord.Message):
            # Ignorer les messages de bots (y compris soi-même)
            if message.author.bot or (self._bot.user and message.author.id == self._bot.user.id):
                return

            if not self.is_user_authorized(message.author.id):
                logger.warning("[discord] Message ignoré (utilisateur %s non autorisé)", message.author.id)
                return

            if not self.is_channel_allowed(message.channel):
                return

            chat_id = str(message.channel.id)
            is_dm = isinstance(message.channel, discord.DMChannel)

            # Émoji ⏱️ si le salon est déjà occupé par une requête en cours
            if self._enable_reactions and chat_id in self._busy_chats:
                with asyncio.suppress(Exception):
                    await message.add_reaction("⏱️")

            raw_text = message.content or ""

            # Traitement asynchrone des pièces jointes
            attachment_injections: List[str] = []
            if message.attachments:
                for att in message.attachments:
                    text_snippet = await download_and_cache_attachment(
                        url=att.url,
                        filename=att.filename,
                        size=att.size,
                        uploads_dir=self._uploads_dir,
                    )
                    if text_snippet:
                        attachment_injections.append(text_snippet)

            full_text = raw_text
            if attachment_injections:
                full_text = f"{raw_text}\n\n" + "\n\n".join(attachment_injections) if raw_text else "\n\n".join(attachment_injections)

            channel_name = getattr(message.channel, "name", "DM")
            source = self.build_source(
                chat_id=chat_id,
                user_id=str(message.author.id),
                user_name=message.author.display_name,
                chat_type="dm" if is_dm else "channel",
                chat_name=channel_name,
                message_id=str(message.id),
            )

            event = MessageEvent(
                source=source,
                text=full_text,
                message_type=MessageType.TEXT,
                reply_to=str(message.reference.message_id) if message.reference and message.reference.message_id else None,
                raw={"message_id": str(message.id), "attachments_count": len(message.attachments)},
            )
            await self.handle_message(event)

        @self._bot.event
        async def on_message_edit(before: discord.Message, after: discord.Message):
            if after.author.bot or (self._bot.user and after.author.id == self._bot.user.id):
                return
            if not self.is_user_authorized(after.author.id):
                return

            new_content = (after.content or "").strip()
            old_content = (before.content or "").strip()

            if not new_content or new_content == old_content:
                return

            await handle_message_edit(
                adapter=self,
                chat_id=str(after.channel.id),
                message_id=str(after.id),
                new_content=new_content,
                sender_id=str(after.author.id),
                sender_name=after.author.display_name,
                is_dm=isinstance(after.channel, discord.DMChannel),
            )

        @self._bot.event
        async def on_message_delete(message: discord.Message):
            author_id = str(message.author.id) if message.author else None
            is_bot = (message.author and message.author.bot) or (self._bot.user and message.author and message.author.id == self._bot.user.id)

            if author_id and not is_bot and not self.is_user_authorized(author_id):
                return

            await handle_message_delete(
                adapter=self,
                chat_id=str(message.channel.id),
                message_id=str(message.id),
                sender_id=author_id or list(self._allowed_users)[0],
                is_dm=isinstance(message.channel, discord.DMChannel),
            )

    def _setup_commands(self) -> None:
        """Enregistre les commandes slash natives Discord via le module commands."""
        setup_all_commands(self._tree, self)

    # =========================================================================
    # Contrôles d'Accès et Filtrage
    # =========================================================================

    def is_user_authorized(self, user_id: Union[int, str]) -> bool:
        """Vérifie si un utilisateur Discord est autorisé à interagir avec le bot."""
        if self._allow_all:
            return True
        return str(user_id) in self._allowed_users

    def is_channel_allowed(self, channel: Any) -> bool:
        """Vérifie si le salon ou fil Discord est autorisé (DM ou fil du forum dédié)."""
        if isinstance(channel, discord.DMChannel):
            return True

        if isinstance(channel, discord.Thread):
            parent_id = str(getattr(channel, "parent_id", ""))
            if self._forum_channel_id and parent_id == self._forum_channel_id:
                return True
            if not self._forum_channel_id:
                return True

        return True

    # =========================================================================
    # Envoi de Messages & Formatage
    # =========================================================================

    async def _resolve_channel(self, chat_id: str) -> Optional[Any]:
        """Résout un objet channel Discord depuis le cache local ou l'API."""
        try:
            cid = int(chat_id)
            c = self._bot.get_channel(cid)
            if c:
                return c
            return await self._bot.fetch_channel(cid)
        except Exception as e:
            logger.debug("[discord] Impossible de résoudre le canal %s : %s", chat_id, e)
            return None

    def _track_bot_replies(self, user_msg_id: str, bot_msg_ids: List[str]) -> None:
        """Enregistre la relation bidirectionnelle entre message utilisateur et réponses du bot."""
        self._reply_map[user_msg_id] = bot_msg_ids
        for b_id in bot_msg_ids:
            self._bot_to_user_map[b_id] = user_msg_id

    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_to: Optional[str] = None,
        parse_mode: Optional[str] = None,
    ) -> SendResult:
        """Envoie un message formaté avec sous-texte de thinking et découpage de code propre."""
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return SendResult(success=False, error=f"Canal {chat_id} introuvable")

        formatted_text = format_thinking_with_subtext(text)
        chunks = split_markdown(formatted_text, max_length=1950)
        if not chunks:
            chunks = [formatted_text]

        attachments: List[discord.File] = []
        is_dm = isinstance(channel, discord.DMChannel)

        ref_message = None
        if reply_to:
            try:
                ref_message = await channel.fetch_message(int(reply_to))
            except Exception:
                ref_message = None

        sent_message_ids: List[str] = []

        for i, chunk in enumerate(chunks):
            is_last = (i == len(chunks) - 1)
            send_kwargs: Dict[str, Any] = {"content": chunk}

            if i == 0 and ref_message:
                send_kwargs["reference"] = ref_message

            if is_last:
                if attachments:
                    send_kwargs["files"] = attachments
                if not is_dm:
                    send_kwargs["view"] = PostResponseActionView(self, chat_id)

            try:
                sent_msg = await channel.send(**send_kwargs)
                sent_message_ids.append(str(sent_msg.id))
            except Exception as e:
                logger.error("[discord] Échec envoi fragment %d : %s", i, e)
                return SendResult(success=False, error=str(e))

        if reply_to and sent_message_ids:
            self._track_bot_replies(str(reply_to), sent_message_ids)

        return SendResult(success=True, message_id=sent_message_ids[0] if sent_message_ids else None)

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Envoie un message sur Discord (implémentation de la méthode abstraite BasePlatformAdapter)."""
        return await self.send_message(chat_id=chat_id, text=content, reply_to=reply_to)


    async def send_typing(self, chat_id: str) -> None:
        """Envoie l'indicateur d'écriture dans le salon spécifié."""
        channel = await self._resolve_channel(chat_id)
        if channel and hasattr(channel, "typing"):
            try:
                await channel.typing()
            except Exception:
                pass

    # =========================================================================
    # Progression des Outils (Tool Progress & Spoiler)
    # =========================================================================

    async def send_tool_progress(
        self,
        chat_id: str,
        tool_name: str,
        tool_args: Optional[str] = None,
        status: str = "running",
        output: Optional[str] = None,
        is_final: bool = False,
    ) -> bool:
        """Met à jour en temps réel la progression des outils ou replie le spoiler final."""
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return False

        output_summary = output
        generated_log_file: Optional[str] = None
        if output and len(output) > 1500:
            saved_summary, saved_path = save_large_output_to_log_file(
                tool_name=tool_name,
                output=output,
                threshold=1500,
                uploads_dir=self._uploads_dir,
            )
            output_summary = saved_summary
            generated_log_file = saved_path

        icon = "✅" if status == "done" else ("❌" if status == "error" else "⏳")
        args_str = f" ({tool_args[:70]})" if tool_args else ""
        step_line = f"• `{tool_name}`{args_str} : {icon}"

        active = self._active_progress.get(chat_id)

        if not active:
            initial_content = f"⚙️ **Exécution d'outils en cours...**\n{step_line}"
            view = ToolProgressView(self, chat_id)
            try:
                sent = await channel.send(content=initial_content, view=view)
                active = {"message_id": sent.id, "steps": [step_line]}
                self._active_progress[chat_id] = active
            except Exception as e:
                logger.debug("[discord] Échec création message de progression : %s", e)
                return False
        else:
            active["steps"].append(step_line)

        if is_final:
            steps_summary = "\n".join(active["steps"][-10:])
            out_preview = f"\n> Sortie : {output_summary[:300]}" if output_summary else ""
            spoiler_content = f"||⚙️ **Journal des outils exécutés :**\n{steps_summary}{out_preview}||"

            try:
                msg = await channel.fetch_message(active["message_id"])
                files = []
                if generated_log_file and Path(generated_log_file).exists():
                    files.append(discord.File(generated_log_file, filename=Path(generated_log_file).name))
                await msg.edit(content=spoiler_content, view=None, attachments=files)
            except Exception as e:
                logger.debug("[discord] Échec repli spoiler outils : %s", e)

            self._active_progress.pop(chat_id, None)
            return True

        current_steps = "\n".join(active["steps"][-4:])
        try:
            msg = await channel.fetch_message(active["message_id"])
            await msg.edit(content=f"⚙️ **Exécution d'outils en cours...**\n{current_steps}")
            return True
        except Exception:
            return False

    async def cancel_active_progress(self, chat_id: str) -> None:
        """Marque la progression active comme interrompue par l'utilisateur."""
        active = self._active_progress.pop(chat_id, None)
        if not active:
            return
        channel = await self._resolve_channel(chat_id)
        if channel:
            try:
                msg = await channel.fetch_message(active["message_id"])
                steps_text = "\n".join(active["steps"][-5:])
                await msg.edit(
                    content=f"||⚠️ **Exécution interrompue par l'utilisateur.**\n{steps_text}||",
                    view=None,
                )
            except Exception:
                pass

    # =========================================================================
    # Gestion des Transitions d'Émojis & Exécution en Arrière-plan
    # =========================================================================

    async def send_turn_start(self, chat_id: str, message_id: str) -> None:
        """Remplace l'émoji ⏱️ par ⏳ pour indiquer le début effectif du tour."""
        if not self._enable_reactions or not message_id:
            return
        self._busy_chats.add(chat_id)
        channel = await self._resolve_channel(chat_id)
        if channel:
            try:
                msg = await channel.fetch_message(int(message_id))
                if self._bot.user:
                    with asyncio.suppress(Exception):
                        await msg.remove_reaction("⏱️", self._bot.user)
                await msg.add_reaction("⏳")
            except Exception:
                pass

    async def send_final_status(self, chat_id: str, message_id: str, success: bool = True) -> None:
        """Remplace l'émoji ⏳ par ✅ (ou ❌) et libère l'état occupé du salon."""
        self._busy_chats.discard(chat_id)
        if not self._enable_reactions or not message_id:
            return
        channel = await self._resolve_channel(chat_id)
        if channel:
            try:
                msg = await channel.fetch_message(int(message_id))
                if self._bot.user:
                    with asyncio.suppress(Exception):
                        await msg.remove_reaction("⏱️", self._bot.user)
                    with asyncio.suppress(Exception):
                        await msg.remove_reaction("⏳", self._bot.user)
                await msg.add_reaction("✅" if success else "❌")
            except Exception:
                pass

    async def _process_message_background(self, event: MessageEvent, session_key: str) -> None:
        """Supervise l'exécution du tour en arrière-plan avec transitions d'émojis."""
        chat_id = str(getattr(event.source, "chat_id", ""))
        msg_id = str(getattr(event.source, "message_id", "") or "")
        if chat_id and msg_id:
            await self.send_turn_start(chat_id, msg_id)
        try:
            await super()._process_message_background(event, session_key)
            if chat_id and msg_id:
                await self.send_final_status(chat_id, msg_id, success=True)
        except Exception:
            if chat_id and msg_id:
                await self.send_final_status(chat_id, msg_id, success=False)
            raise

    # =========================================================================
    # Questions Interactives (pi-bridge style) & Clarifications
    # =========================================================================

    async def ask_question(
        self,
        chat_id: str,
        question: str,
        options: Optional[List[Dict[str, Any]]] = None,
        details: Optional[str] = None,
        context: Optional[str] = None,
        multi_select: bool = False,
        timeout_seconds: Optional[int] = None,
        reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Pose une question interactive avec boutons, menus déroulants et modales de texte libre."""
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return {"status": "cancelled", "answers": [], "error": f"Canal {chat_id} introuvable"}

        view = QuestionInteractiveView(
            adapter=self,
            chat_id=chat_id,
            question=question,
            options=options,
            details=details,
            context=context,
            multi_select=multi_select,
            timeout_seconds=timeout_seconds,
        )

        send_kwargs: Dict[str, Any] = {
            "embed": view.build_main_embed(),
            "view": view,
        }
        if reply_to:
            try:
                ref = await channel.fetch_message(int(reply_to))
                send_kwargs["reference"] = ref
            except Exception:
                pass

        try:
            msg = await channel.send(**send_kwargs)
            view.message = msg
            return await view.future
        except Exception as e:
            logger.error("[discord] Échec lors de la question interactive : %s", e)
            return {"status": "cancelled", "answers": [], "error": str(e)}

    async def send_clarify(
        self,
        chat_id: str,
        question: str,
        options: List[Dict[str, Any]],
        reply_to: Optional[str] = None,
        details: Optional[str] = None,
        context: Optional[str] = None,
        multi_select: bool = False,
        timeout_seconds: Optional[int] = None,
    ) -> SendResult:
        """Affiche les options de clarification style pi-bridge."""
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return SendResult(success=False, error=f"Canal {chat_id} introuvable")

        view = QuestionInteractiveView(
            adapter=self,
            chat_id=chat_id,
            question=question,
            options=options,
            details=details,
            context=context,
            multi_select=multi_select,
            timeout_seconds=timeout_seconds,
        )

        send_kwargs: Dict[str, Any] = {
            "embed": view.build_main_embed(),
            "view": view,
        }
        if reply_to:
            try:
                ref = await channel.fetch_message(int(reply_to))
                send_kwargs["reference"] = ref
            except Exception:
                pass

        try:
            msg = await channel.send(**send_kwargs)
            view.message = msg
            return SendResult(success=True, message_id=str(msg.id))
        except Exception as e:
            return SendResult(success=False, error=str(e))

    async def send_exec_approval(
        self,
        chat_id: str,
        command: str,
        timeout_seconds: float = 300.0,
        reply_to: Optional[str] = None,
    ) -> bool:
        """Affiche des boutons interactifs pour valider ou rejeter une commande sensible."""
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return False

        view = ApprovalView(self, chat_id, timeout=timeout_seconds)
        content = f"⚠️ **Demande d'approbation d'exécution :**\n```bash\n{command}\n```"

        send_kwargs: Dict[str, Any] = {"content": content, "view": view}
        if reply_to:
            try:
                ref = await channel.fetch_message(int(reply_to))
                send_kwargs["reference"] = ref
            except Exception:
                pass

        try:
            await channel.send(**send_kwargs)
            return await view.future
        except Exception as e:
            logger.error("[discord] Échec demande approbation : %s", e)
            return False

    async def send_alert(
        self,
        text: str,
        level: str = "info",
        task_id: Optional[str] = None,
    ) -> SendResult:
        """Achemine une alerte critique en DM privé."""
        target_dm_id = list(self._allowed_users)[0] if self._allowed_users else None
        if not target_dm_id:
            return SendResult(success=False, error="Aucun utilisateur cible configuré pour les alertes")

        try:
            user = await self._bot.fetch_user(int(target_dm_id))
            if not user:
                return SendResult(success=False, error=f"Utilisateur {target_dm_id} introuvable")

            color_map = {
                "error": 0xED4245,
                "critical": 0xED4245,
                "warning": 0xFEE75C,
                "info": 0x5865F2,
            }
            embed = discord.Embed(
                title=f"🚨 Alerte Système Hermes [{level.upper()}]",
                description=text,
                color=color_map.get(level.lower(), 0x5865F2),
            )
            view = SystemAlertView(self, task_id or "") if task_id else None
            msg = await user.send(embed=embed, view=view)
            return SendResult(success=True, message_id=str(msg.id))
        except Exception as e:
            logger.error("[discord] Échec envoi alerte DM : %s", e)
            return SendResult(success=False, error=str(e))

    async def delete_message(self, chat_id: str, message_id: str) -> bool:
        """Supprime un message Discord par son ID."""
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return False
        try:
            msg = await channel.fetch_message(int(message_id))
            await msg.delete()
            return True
        except Exception:
            return False

    # =========================================================================
    # Délégations Services (Cron, Sessions Forum)
    # =========================================================================

    def fetch_cron_jobs(self) -> List[Dict[str, Any]]:
        """Récupère la liste des tâches planifiées depuis le service cron."""
        return fetch_cron_jobs()

    async def handle_cron_action(self, action: str, job_id: str, chat_id: str) -> None:
        """Exécute une action sur une tâche Cron via le service cron."""
        await handle_cron_action(action, job_id, chat_id)

    async def handle_cron_create(self, name: str, schedule: str, prompt: str, deliver: str, chat_id: str) -> None:
        """Crée une nouvelle tâche cron via le service cron."""
        await handle_cron_create(name, schedule, prompt, deliver, chat_id)

    def get_cron_last_output(self, job_id: str) -> Optional[str]:
        """Récupère le dernier rapport d'exécution sauvegardé pour une tâche cron."""
        return get_cron_last_output(job_id)

    async def fetch_forum_threads(self) -> List[discord.Thread]:
        """Récupère les fils de discussion du forum via le service de sessions."""
        return await fetch_forum_threads(self._bot, self._forum_channel_id)

    async def purge_session(self, chat_id: str) -> None:
        """Supprime une session dans SessionDB lors de la suppression d'un fil."""
        await purge_session(self, chat_id)

    # =========================================================================
    # Dispatch Actions & Commandes vers Hermes
    # =========================================================================

    async def dispatch_command_action(
        self,
        command: str,
        args: str,
        chat_id: str,
        user_id: str,
        user_name: str,
    ) -> None:
        """Transmet une commande slash vers Hermes sous forme de MessageEvent."""
        cmd_text = f"/{command} {args}".strip() if args else f"/{command}"
        source = self.build_source(
            chat_id=chat_id,
            user_id=user_id,
            user_name=user_name,
            chat_type="channel",
            chat_name="ForumSession",
        )
        event = MessageEvent(
            source=source,
            text=cmd_text,
            message_type=MessageType.COMMAND,
            raw={"command": command, "args": args},
        )
        await self.handle_message(event)

    async def dispatch_button_action(
        self,
        action: str,
        chat_id: str,
        user_id: str,
        user_name: str,
        payload: str = "",
        interaction_message: Optional[discord.Message] = None,
    ) -> None:
        """Transmet une action de bouton vers Hermes sous forme de MessageEvent."""
        if action == "regenerate":
            btn_text = "Régénère la réponse précédente."
        elif action == "close":
            btn_text = "/close"
        elif action == "view_logs":
            btn_text = "Affiche les 50 dernières lignes de logs système."
        elif action == "retry_task":
            btn_text = f"Relance la tâche {payload}." if payload else "Relance la tâche précédente."
        else:
            btn_text = payload or action

        source = self.build_source(
            chat_id=chat_id,
            user_id=user_id,
            user_name=user_name,
            chat_type="channel",
            chat_name="ForumSession",
            message_id=str(interaction_message.id) if interaction_message else None,
        )
        event = MessageEvent(
            source=source,
            text=btn_text,
            message_type=MessageType.TEXT,
            raw={"action": action, "payload": payload},
        )
        await self.handle_message(event)

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Récupère les informations d'un canal Discord."""
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return {"name": "unknown", "type": "unknown", "chat_id": chat_id}
        name = getattr(channel, "name", "DM")
        ctype = "dm" if isinstance(channel, discord.DMChannel) else "channel"
        return {"name": name, "type": ctype, "chat_id": chat_id}

    # =========================================================================
    # Cycle de Vie Asynchrone de l'Adaptateur
    # =========================================================================

    async def connect(self) -> bool:
        """Démarre le bot Discord en tâche de fond asynchrone."""
        if not self._bot_token:
            logger.error("[discord] DISCORD_BOT_TOKEN non configuré. Impossible de connecter le bot.")
            return False

        logger.info("[discord] Démarrage du bot discord.py...")

        async def _run_bot():
            try:
                await self._bot.start(self._bot_token)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error("[discord] Erreur d'exécution du bot discord.py : %s", e)

        self._main_task = asyncio.create_task(_run_bot())
        self._running = True
        return True

    async def disconnect(self) -> None:
        """Arrête proprement le bot Discord."""
        logger.info("[discord] Fermeture de la connexion discord.py...")
        self._running = False
        if self._bot and not self._bot.is_closed():
            await self._bot.close()
        if self._main_task and not self._main_task.done():
            self._main_task.cancel()
            with asyncio.suppress(asyncio.CancelledError):
                await self._main_task
        logger.info("[discord] Connexion discord.py arrêtée.")


def register(ctx) -> None:
    """Point d'entrée du plugin appelé par le système de découverte d'Hermes Agent."""
    ctx.register_platform(
        name="discord-py",
        label="Discord (discord.py fine-tuned)",
        adapter_factory=lambda cfg: DiscordPyAdapter(cfg),
        check_fn=check_discord_requirements,
        required_env=["DISCORD_BOT_TOKEN"],
        allowed_users_env="DISCORD_ALLOWED_USERS",
        allow_all_env="DISCORD_ALLOW_ALL_USERS",
        cron_deliver_env_var="DISCORD_HOME_CHANNEL",
        max_message_length=2000,
        emoji="",
        allow_update_command=True,
    )
    # Enregistre également sous discord pour remplacer directement l'adaptateur par défaut
    ctx.register_platform(
        name="discord",
        label="Discord (discord.py fine-tuned)",
        adapter_factory=lambda cfg: DiscordPyAdapter(cfg),
        check_fn=check_discord_requirements,
        required_env=["DISCORD_BOT_TOKEN"],
        allowed_users_env="DISCORD_ALLOWED_USERS",
        allow_all_env="DISCORD_ALLOW_ALL_USERS",
        cron_deliver_env_var="DISCORD_HOME_CHANNEL",
        max_message_length=2000,
        emoji="",
        allow_update_command=True,
    )
    # Enregistre également sous discord-js pour compatibilité avec d'anciennes configs
    ctx.register_platform(
        name="discord-js",
        label="Discord (discord.py fine-tuned)",
        adapter_factory=lambda cfg: DiscordPyAdapter(cfg),
        check_fn=check_discord_requirements,
        required_env=["DISCORD_BOT_TOKEN"],
        allowed_users_env="DISCORD_ALLOWED_USERS",
        allow_all_env="DISCORD_ALLOW_ALL_USERS",
        cron_deliver_env_var="DISCORD_HOME_CHANNEL",
        max_message_length=2000,
        emoji="",
        allow_update_command=True,
    )
