"""Adaptateur de plateforme Discord.js pour Hermes Agent.

Fait le pont entre Hermes Agent et un processus sidecar Node.js exécutant discord.js.
Les messages entrants transitent via un flux SSE sur la boucle locale (GET /inbound).
Les messages sortants et actions transitent via des requêtes HTTP POST locales.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)

logger = logging.getLogger(__name__)

_DEFAULT_SIDECAR_PORT = 8790
_SIDECAR_DIR = Path(__file__).parent / "sidecar"
_DEFAULT_ALLOWED_USER = "544862774002581504"
_DEFAULT_FORUM_CHANNEL = "1544452203207589938"


def _find_node() -> Optional[str]:
    """Trouve l'exécutable node sur le PATH ou via les constantes Hermes."""
    try:
        from hermes_constants import find_node_executable
        node = find_node_executable("node")
        if node:
            return node
    except Exception:
        pass
    return shutil.which("node")


def _find_npm() -> Optional[str]:
    """Trouve l'exécutable npm sur le PATH ou via les constantes Hermes."""
    try:
        from hermes_constants import find_node_executable
        npm = find_node_executable("npm")
        if npm:
            return npm
    except Exception:
        pass
    return shutil.which("npm")


def check_requirements() -> bool:
    """Vérifie si l'environnement Node.js est disponible pour le sidecar."""
    return _find_node() is not None


class DiscordJsAdapter(BasePlatformAdapter):
    """Adaptateur de plateforme reliant Hermes à un sidecar Node.js discord.js fine-tuné."""

    def __init__(self, config: PlatformConfig):
        platform = Platform.DISCORD if hasattr(Platform, "DISCORD") else Platform("discord")
        super().__init__(config, platform)
        self._port = int(os.environ.get("HERMES_DISCORD_JS_PORT", _DEFAULT_SIDECAR_PORT))
        self._token = secrets.token_hex(16)
        self._proc: Optional[subprocess.Popen] = None
        self._inbound_task: Optional[asyncio.Task] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._bot_token = os.environ.get("DISCORD_BOT_TOKEN", "")
        self._allowed_user = os.environ.get("DISCORD_ALLOWED_USERS", _DEFAULT_ALLOWED_USER).split(",")[0].strip()
        self._forum_channel = os.environ.get("DISCORD_FORUM_CHANNEL_ID", _DEFAULT_FORUM_CHANNEL).strip()
        self._reply_map: Dict[str, List[str]] = {}
        self._bot_to_user_map: Dict[str, str] = {}
        # Mode file d'attente (queue) : les nouveaux messages reçus pendant qu'un tour s'exécute
        # sont mis en attente et exécutés séquentiellement au tour suivant sans interrompre la tâche en cours.
        self._busy_text_mode = "queue"
        self._busy_input_mode = "queue"

    @property
    def _base_url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    @property
    def _headers(self) -> Dict[str, str]:
        return {"x-hermes-token": self._token}

    def _ensure_sidecar_deps(self) -> None:
        """Installe les dépendances via npm ci/install et compile le sidecar si nécessaire."""
        node_modules = _SIDECAR_DIR / "node_modules"
        dist = _SIDECAR_DIR / "dist"

        npm = _find_npm()
        if not npm:
            logger.warning("[discord-js] npm non trouvé ; installation automatique ignorée")
            return

        if not node_modules.is_dir():
            logger.info("[discord-js] Installation des dépendances du sidecar via npm ci...")
            res = subprocess.run([npm, "ci"], cwd=str(_SIDECAR_DIR), capture_output=True, text=True)
            if res.returncode != 0:
                logger.warning("[discord-js] Échec de npm ci, bascule vers npm install...")
                subprocess.run([npm, "install"], cwd=str(_SIDECAR_DIR), check=False)

        if not dist.is_dir() or not (dist / "index.js").exists():
            logger.info("[discord-js] Compilation du sidecar TypeScript...")
            subprocess.run([npm, "run", "build"], cwd=str(_SIDECAR_DIR), check=False)

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        """Démarre le processus sidecar et écoute les événements entrants."""
        node = _find_node()
        if not node:
            logger.error("[discord-js] Node.js n'est pas installé ou introuvable.")
            return False

        self._ensure_sidecar_deps()

        env = os.environ.copy()
        env["HERMES_SIDECAR_PORT"] = str(self._port)
        env["HERMES_SIDECAR_TOKEN"] = self._token
        env["DISCORD_ALLOWED_USERS"] = self._allowed_user
        env["DISCORD_FORUM_CHANNEL_ID"] = self._forum_channel
        env["HERMES_UPLOADS_DIR"] = os.environ.get("HERMES_UPLOADS_DIR", "/workspace/uploads")
        if self._bot_token:
            env["DISCORD_BOT_TOKEN"] = self._bot_token

        dist_entry = _SIDECAR_DIR / "dist" / "index.js"
        src_entry = _SIDECAR_DIR / "src" / "index.ts"

        if dist_entry.exists():
            cmd = [node, str(dist_entry)]
        else:
            npx = shutil.which("npx") or "npx"
            cmd = [npx, "tsx", str(src_entry)]

        logger.info("[discord-js] Lancement du sidecar discord.js : %s", " ".join(cmd))
        self._proc = subprocess.Popen(
            cmd,
            cwd=str(_SIDECAR_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self._client = httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=30.0)

        connected = False
        for _ in range(30):
            await asyncio.sleep(0.5)
            if self._proc.poll() is not None:
                stderr = self._proc.stderr.read().decode("utf-8", errors="replace") if self._proc.stderr else ""
                logger.error("[discord-js] Le sidecar s'est arrêté prématurément : %s", stderr)
                return False
            try:
                resp = await self._client.get("/healthz")
                if resp.status_code == 200:
                    connected = True
                    break
            except httpx.RequestError:
                continue

        if not connected:
            logger.error("[discord-js] Délai dépassé lors du contrôle de santé du sidecar.")
            self._proc.kill()
            return False

        self._inbound_task = asyncio.create_task(self._listen_inbound())
        self._mark_connected()
        logger.info("[discord-js] Sidecar connecté et opérationnel sur le port %d", self._port)
        asyncio.create_task(self._sync_cron_jobs_to_sidecar())
        return True

    async def _listen_inbound(self) -> None:
        """Écoute le flux d'événements entrants depuis le endpoint SSE du sidecar."""
        while self.is_connected and self._client:
            try:
                async with self._client.stream("GET", "/inbound", timeout=None) as response:
                    async for line in response.aiter_lines():
                        if not line or line.startswith(":"):
                            continue
                        if line.startswith("data: "):
                            raw_data = line[6:]
                            try:
                                payload = json.loads(raw_data)
                                await self._handle_sidecar_event(payload)
                            except Exception as e:
                                logger.warning("[discord-js] Événement malformé reçu du sidecar : %s", e)
            except (httpx.RequestError, asyncio.CancelledError):
                if not self.is_connected:
                    break
                await asyncio.sleep(1.0)

    async def _handle_sidecar_event(self, data: Dict[str, Any]) -> None:
        """Convertit l'événement JSON du sidecar (message, commande slash, bouton) en MessageEvent Hermes."""
        event_type = data.get("type", "message")
        chat_id = str(data.get("chat_id", ""))
        sender_id = str(data.get("sender_id", ""))
        sender_name = str(data.get("sender_name", ""))
        is_dm = bool(data.get("is_dm", False))

        # 1. Message standard
        if event_type == "message":
            content = str(data.get("content", ""))
            message_id = str(data.get("message_id", ""))

            source = self.build_source(
                chat_id=chat_id,
                user_id=sender_id,
                user_name=sender_name,
                chat_type="dm" if is_dm else "channel",
                channel_name=data.get("channel_name", ""),
                message_id=message_id,
            )

            event = MessageEvent(
                source=source,
                text=content,
                message_type=MessageType.TEXT,
                reply_to=data.get("reply_to_id"),
                raw=data,
            )
            await self.handle_message(event)
            return

        # 2. Commande Slash (/close, /reset, /model)
        if event_type == "command":
            command = data.get("command", "")
            args = data.get("args", "")

            source = self.build_source(
                chat_id=chat_id,
                user_id=sender_id,
                user_name=sender_name,
                chat_type="dm" if is_dm else "channel",
                channel_name="ForumSession",
                message_id=str(data.get("interaction_id", "")),
            )

            cmd_text = f"/{command} {args}".strip() if args else f"/{command}"
            event = MessageEvent(
                source=source,
                text=cmd_text,
                message_type=MessageType.COMMAND,
                raw=data,
            )
            await self.handle_message(event)
            return

        # 3. Clic sur bouton interactif (approbation, clarification, annulation, régénération, logs)
        if event_type == "button":
            action = data.get("action", "")
            payload = data.get("payload", "")

            # Interprétation de l'action
            if action == "approval":
                is_approved = payload.startswith("approve")
                btn_text = "yes" if is_approved else "no"
            elif action == "clarify":
                btn_text = payload
            elif action == "cancel":
                btn_text = "/stop"
            elif action == "regenerate":
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
                user_id=sender_id,
                user_name=sender_name or "user",
                chat_type="dm" if is_dm else "channel",
                channel_name=data.get("channel_name", "session"),
                message_id=str(data.get("message_id", "")),
            )

            event = MessageEvent(
                source=source,
                text=btn_text,
                message_type=MessageType.TEXT,
                raw=data,
            )
            await self.handle_message(event)
            return

        # 4. Suppression de message sur Discord
        if event_type == "message_delete":
            message_id = str(data.get("message_id", ""))
            await self._handle_message_delete(chat_id, message_id, sender_id, is_dm)
            return

        # 5. Modification de message sur Discord (édite dans la session et relance la régénération)
        if event_type == "message_edit":
            message_id = str(data.get("message_id", ""))
            new_content = str(data.get("content", ""))
            await self._handle_message_edit(
                chat_id, message_id, new_content, sender_id, sender_name, is_dm, data
            )
            return

        # 6. Suppression de session depuis le gestionnaire /sessions
        if event_type == "session_delete":
            session_id = str(data.get("session_id", ""))
            await self._handle_session_delete(session_id)
            return

        # 7. Gestion des tâches Cron (/cron)
        if event_type == "cron":
            await self._handle_cron_event(data)
            return

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Envoie un message via le sidecar avec routage intelligent (DMs pour système / forum pour sessions)."""
        if not self._client:
            return SendResult(success=False, error="Client sidecar non initialisé")

        target_chat_id = chat_id
        # Routage vers DM si chat_id correspond à l'utilisateur ou est marqué 'dm'
        if chat_id in (self._allowed_user, "dm", ""):
            target_chat_id = self._allowed_user

        try:
            resp = await self._client.post(
                "/send",
                json={
                    "chat_id": target_chat_id,
                    "content": content,
                    "reply_to": reply_to,
                    "metadata": metadata or {},
                },
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("success"):
                msg_ids = data.get("message_ids") or [data.get("message_id")]
                valid_ids = [str(m) for m in msg_ids if m]
                if reply_to and valid_ids:
                    self._track_bot_replies(str(reply_to), valid_ids)
                return SendResult(success=True, message_id=valid_ids[0] if valid_ids else None)
            return SendResult(success=False, error=data.get("error", "Erreur inconnue"))
        except Exception as e:
            logger.error("[discord-js] Échec lors de l'envoi du message : %s", e)
            return SendResult(success=False, error=str(e))

    async def _process_message_background(self, event: MessageEvent, session_key: str) -> None:
        """Gère l'exécution du tour en arrière-plan avec transitions d'émojis (⏱️ -> ⏳ -> ✅)."""
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

    def _fetch_cron_jobs(self) -> List[Dict[str, Any]]:
        """Récupère la liste des tâches planifiées enregistrées dans Hermes."""
        try:
            from cron import jobs as cron_jobs
            if not cron_jobs:
                return []
            raw_jobs = cron_jobs.list_jobs(include_disabled=True)
            jobs = []
            for j in raw_jobs:
                jobs.append({
                    "id": str(j.get("id", "")),
                    "name": str(j.get("name") or (j.get("prompt", "")[:30] if j.get("prompt") else "Sans titre")),
                    "schedule": str(j.get("schedule", "")),
                    "schedule_display": str(j.get("schedule_display") or j.get("schedule", "")),
                    "prompt": str(j.get("prompt", "")),
                    "enabled": bool(j.get("enabled", True)),
                    "last_run": j.get("last_run"),
                    "last_status": j.get("last_status"),
                    "next_run": j.get("next_run"),
                    "deliver": str(j.get("deliver", "")),
                })
            return jobs
        except Exception as e:
            logger.debug("[discord-js] Échec list_jobs : %s", e)
            return []

    async def _sync_cron_jobs_to_sidecar(self) -> None:
        """Transmet la liste actuelle des tâches cron au sidecar pour mise en cache."""
        if not self._client:
            return
        jobs = self._fetch_cron_jobs()
        try:
            await self._client.post("/cron/sync", json={"jobs": jobs})
        except Exception as e:
            logger.debug("[discord-js] Échec synchronisation cron vers sidecar : %s", e)

    async def _handle_cron_event(self, data: Dict[str, Any]) -> None:
        """Traite les actions et requêtes sur les tâches Cron (list, pause, resume, trigger, delete, create, view_output)."""
        action = data.get("action", "list")
        job_id = data.get("job_id", "")
        chat_id = data.get("chat_id", "")

        logger.info("[discord-js] Action Cron reçue : %s (job_id=%s)", action, job_id)

        try:
            from cron import jobs as cron_jobs
        except ImportError:
            cron_jobs = None

        if action == "list":
            await self._sync_cron_jobs_to_sidecar()
            return

        if action == "pause" and cron_jobs and job_id:
            try:
                cron_jobs.pause_job(job_id)
            except Exception as e:
                logger.warning("[discord-js] Échec pause_job %s : %s", job_id, e)
            await self._sync_cron_jobs_to_sidecar()
            return

        if action == "resume" and cron_jobs and job_id:
            try:
                cron_jobs.resume_job(job_id)
            except Exception as e:
                logger.warning("[discord-js] Échec resume_job %s : %s", job_id, e)
            await self._sync_cron_jobs_to_sidecar()
            return

        if action == "trigger" and cron_jobs and job_id:
            try:
                if hasattr(cron_jobs, "trigger_job"):
                    cron_jobs.trigger_job(job_id)
                elif hasattr(cron_jobs, "run_job"):
                    cron_jobs.run_job(job_id)
                else:
                    logger.warning("[discord-js] trigger_job non disponible")
            except Exception as e:
                logger.warning("[discord-js] Échec trigger_job %s : %s", job_id, e)
            await self._sync_cron_jobs_to_sidecar()
            return

        if action == "delete" and cron_jobs and job_id:
            try:
                cron_jobs.remove_job(job_id)
            except Exception as e:
                logger.warning("[discord-js] Échec remove_job %s : %s", job_id, e)
            await self._sync_cron_jobs_to_sidecar()
            return

        if action == "create" and cron_jobs:
            name = data.get("name", "")
            schedule = data.get("schedule", "")
            prompt = data.get("prompt", "")
            deliver = data.get("deliver") or chat_id
            try:
                cron_jobs.create_job(prompt=prompt, schedule=schedule, name=name, deliver=deliver)
            except Exception as e:
                logger.warning("[discord-js] Échec create_job : %s", e)
            await self._sync_cron_jobs_to_sidecar()
            return

        if action == "view_output" and job_id:
            output_text = None
            try:
                from pathlib import Path
                from hermes_cli.config import get_hermes_home
                output_dir = Path(get_hermes_home()) / "cron" / "output" / job_id
                if output_dir.exists():
                    files = sorted(output_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
                    if files:
                        output_text = files[0].read_text(encoding="utf-8")[:1800]
            except Exception as e:
                logger.debug("[discord-js] Lecture output cron échouée : %s", e)
            if output_text:
                await self.send(
                    chat_id=chat_id,
                    content=f"📜 **Dernier rapport d'exécution pour la tâche `{job_id}` :**\n```markdown\n{output_text}\n```",
                )
            else:
                await self.send(
                    chat_id=chat_id,
                    content=f"ℹ️ Aucun rapport d'exécution disponible pour la tâche `{job_id}`.",
                )
            return

    async def _handle_session_delete(self, chat_id: str) -> None:
        """Supprime la session dans Hermes SessionDB lorsque le fil Discord est supprimé."""
        logger.info("[discord-js] Traitement suppression de session pour chat_id=%s", chat_id)
        session_id = await self._get_session_id_for_chat(chat_id)
        target_id = session_id or chat_id
        try:
            from hermes_state import SessionDB
            db = SessionDB()
            if hasattr(db, "delete_session"):
                db.delete_session(target_id)
                logger.info("[discord-js] Session %s supprimée de SessionDB", target_id)
        except Exception as e:
            logger.warning("[discord-js] Échec suppression session %s dans SessionDB : %s", target_id, e)

    def _track_bot_replies(self, user_msg_id: str, bot_msg_ids: List[str]) -> None:
        """Enregistre la correspondance entre un message utilisateur et les réponses envoyées par le bot."""
        if not user_msg_id:
            return
        if user_msg_id not in self._reply_map:
            self._reply_map[user_msg_id] = []
        for mid in bot_msg_ids:
            if mid and mid not in self._reply_map[user_msg_id]:
                self._reply_map[user_msg_id].append(mid)
            self._bot_to_user_map[mid] = user_msg_id

    async def delete_message(self, chat_id: str, message_id: str) -> bool:
        """Supprime un message Discord via le sidecar."""
        if not self._client or not message_id:
            return False
        try:
            resp = await self._client.post(
                "/delete_message",
                json={"chat_id": chat_id, "message_id": message_id},
            )
            return resp.status_code == 200 and resp.json().get("success", False)
        except Exception as e:
            logger.warning("[discord-js] Échec suppression message %s : %s", message_id, e)
            return False

    async def _resolve_session_id(self, chat_id: str, sender_id: str, is_dm: bool) -> Optional[str]:
        """Résout l'identifiant de session Hermes pour un salon donné."""
        source = self.build_source(
            chat_id=chat_id,
            user_id=sender_id,
            user_name="Flo",
            chat_type="dm" if is_dm else "channel",
            channel_name="ForumSession",
        )
        if hasattr(self, "_session_store") and self._session_store:
            try:
                if hasattr(self._session_store, "get_or_create_session"):
                    entry = self._session_store.get_or_create_session(source)
                    if inspect.isawaitable(entry):
                        entry = await entry
                    if entry and getattr(entry, "session_id", None):
                        return entry.session_id
            except Exception as e:
                logger.debug("[discord-js] get_or_create_session via session_store failed: %s", e)
        try:
            from hermes_state import SessionDB
            db = SessionDB()
            finder = getattr(db, "find_session_by_origin", None)
            if callable(finder):
                sid = finder(platform="discord", chat_id=chat_id)
                if sid:
                    return sid
        except Exception as e:
            logger.debug("[discord-js] find_session_by_origin failed: %s", e)
        return None

    async def _load_session_transcript(self, session_id: str) -> List[Dict[str, Any]]:
        """Charge l'historique complet des messages d'une session."""
        if hasattr(self, "_session_store") and self._session_store:
            try:
                if hasattr(self._session_store, "load_transcript"):
                    res = self._session_store.load_transcript(session_id)
                    if inspect.isawaitable(res):
                        return await res
                    return res
            except Exception as e:
                logger.debug("[discord-js] load_transcript via session_store failed: %s", e)
        try:
            from hermes_state import SessionDB
            db = SessionDB()
            return db.get_messages(session_id, include_inactive=False)
        except Exception as e:
            logger.warning("[discord-js] Échec chargement transcript : %s", e)
            return []

    async def _rewrite_session_transcript(self, session_id: str, messages: List[Dict[str, Any]]) -> bool:
        """Réécrit l'historique actif de la session avec la liste de messages mise à jour."""
        if hasattr(self, "_session_store") and self._session_store:
            try:
                if hasattr(self._session_store, "rewrite_transcript"):
                    res = self._session_store.rewrite_transcript(session_id, messages, active_only=True)
                    if inspect.isawaitable(res):
                        return await res
                    return bool(res)
            except Exception as e:
                logger.debug("[discord-js] rewrite_transcript via session_store failed: %s", e)
        try:
            from hermes_state import SessionDB
            db = SessionDB()
            db.replace_messages(session_id, messages, active_only=True)
            return True
        except Exception as e:
            logger.warning("[discord-js] Échec réécriture transcript : %s", e)
            return False

    async def _handle_message_delete(self, chat_id: str, message_id: str, sender_id: str, is_dm: bool) -> None:
        """Supprime le tour complet dans la session et sur Discord lors d'une suppression de message."""
        logger.info("[discord-js] Traitement suppression message_id=%s dans chat_id=%s", message_id, chat_id)

        # 1. Si une exécution est en cours, interruption immédiate
        source = self.build_source(
            chat_id=chat_id,
            user_id=sender_id,
            user_name="System",
            chat_type="dm" if is_dm else "channel",
            channel_name="ForumSession",
            message_id=message_id,
        )
        try:
            await self.handle_message(MessageEvent(source=source, text="/stop", message_type=MessageType.COMMAND))
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.debug("[discord-js] Interruption tâche en cours : %s", e)

        # 2. Résolution de la session
        session_id = await self._resolve_session_id(chat_id, sender_id, is_dm)
        if not session_id:
            logger.warning("[discord-js] Session introuvable pour chat_id=%s", chat_id)
            return

        # 3. Chargement de l'historique
        transcript = await self._load_session_transcript(session_id)
        if not transcript:
            return

        # 4. Localisation du message ciblé
        target_idx = None
        target_role = None
        for i, entry in enumerate(transcript):
            mid = str(entry.get("message_id") or entry.get("platform_message_id") or "")
            if mid == message_id:
                target_idx = i
                target_role = entry.get("role")
                break

        # Vérification si message_id correspond à une réponse de bot indexée
        if target_idx is None and message_id in self._bot_to_user_map:
            mapped_uid = self._bot_to_user_map[message_id]
            for i, entry in enumerate(transcript):
                mid = str(entry.get("message_id") or entry.get("platform_message_id") or "")
                if mid == mapped_uid:
                    target_idx = i
                    target_role = entry.get("role")
                    break

        if target_idx is None:
            logger.info("[discord-js] Message %s introuvable dans transcript de session %s", message_id, session_id)
            return

        # 5. Suppression selon le rôle
        if target_role == "assistant":
            new_transcript = [e for i, e in enumerate(transcript) if i != target_idx]
            await self._rewrite_session_transcript(session_id, new_transcript)
            logger.info("[discord-js] Réponse assistant retirée de la session %s", session_id)
        else:
            # Tour complet : supprimer le(s) message(s) de réponse du bot sur Discord
            bot_reply_ids = self._reply_map.get(message_id, [])
            for b_id in bot_reply_ids:
                await self.delete_message(chat_id, b_id)
            self._reply_map.pop(message_id, None)

            # Supprimer de l'historique jusqu'au prochain message utilisateur
            turn_end = target_idx + 1
            while turn_end < len(transcript) and transcript[turn_end].get("role") != "user":
                turn_end += 1

            new_transcript = transcript[:target_idx] + transcript[turn_end:]
            await self._rewrite_session_transcript(session_id, new_transcript)
            logger.info(
                "[discord-js] Tour complet supprimé de la session %s (indices %d à %d)",
                session_id,
                target_idx,
                turn_end - 1,
            )

    async def _handle_message_edit(
        self,
        chat_id: str,
        message_id: str,
        new_content: str,
        sender_id: str,
        sender_name: str,
        is_dm: bool,
        raw_data: Dict[str, Any],
    ) -> None:
        """Tronque l'historique à partir du message édité, nettoie Discord et relance la génération."""
        logger.info(
            "[discord-js] Traitement modification message_id=%s dans chat_id=%s: %s",
            message_id,
            chat_id,
            new_content[:80],
        )

        # 1. Si une exécution est en cours, interruption immédiate (/stop)
        source = self.build_source(
            chat_id=chat_id,
            user_id=sender_id,
            user_name=sender_name,
            chat_type="dm" if is_dm else "channel",
            channel_name=raw_data.get("channel_name", "ForumSession"),
            message_id=message_id,
        )
        try:
            await self.handle_message(MessageEvent(source=source, text="/stop", message_type=MessageType.COMMAND))
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.debug("[discord-js] Interruption tâche en cours : %s", e)

        # 2. Résolution de la session
        session_id = await self._resolve_session_id(chat_id, sender_id, is_dm)
        if not session_id:
            logger.warning("[discord-js] Session introuvable pour chat_id=%s", chat_id)
            return

        # 3. Chargement de l'historique
        transcript = await self._load_session_transcript(session_id)
        if not transcript:
            return

        # 4. Recherche de l'index du message utilisateur à modifier
        target_idx = None
        for i, entry in enumerate(transcript):
            mid = str(entry.get("message_id") or entry.get("platform_message_id") or "")
            if mid == message_id:
                target_idx = i
                break

        if target_idx is None:
            # Fallback sur le dernier message utilisateur
            for i in range(len(transcript) - 1, -1, -1):
                if transcript[i].get("role") == "user":
                    target_idx = i
                    break

        if target_idx is None:
            logger.warning("[discord-js] Aucun message à modifier dans la session %s", session_id)
            return

        # 5. Supprimer l'ancienne réponse du bot sur Discord
        bot_reply_ids = self._reply_map.get(message_id, [])
        for b_id in bot_reply_ids:
            await self.delete_message(chat_id, b_id)
        self._reply_map.pop(message_id, None)

        # 6. Tronquer l'historique à partir de ce message
        truncated_transcript = transcript[:target_idx]
        await self._rewrite_session_transcript(session_id, truncated_transcript)
        logger.info(
            "[discord-js] Historique tronqué à l'index %d (%d messages conservés). Relance régénération.",
            target_idx,
            len(truncated_transcript),
        )

        # 7. Relancer le cycle de génération avec le texte édité
        event = MessageEvent(
            source=source,
            text=new_content,
            message_type=MessageType.TEXT,
            reply_to=raw_data.get("reply_to_id"),
            raw=raw_data,
        )
        await self.handle_message(event)

    async def send_turn_start(self, chat_id: str, message_id: str) -> None:
        """Indique le démarrage effectif d'un tour pour remplacer ⏱️ par ⏳."""
        if not self._client or not message_id:
            return
        try:
            await self._client.post(
                "/turn_start",
                json={"chat_id": chat_id, "message_id": message_id},
            )
        except Exception:
            pass

    async def send_final_status(self, chat_id: str, message_id: str, success: bool = True) -> None:
        """Remplace l'émoji ⏳ par ✅ (ou ❌) et libère l'état occupé du salon."""
        if not self._client or not message_id:
            return
        try:
            await self._client.post(
                "/final_status",
                json={"chat_id": chat_id, "message_id": message_id, "success": success},
            )
        except Exception:
            pass

    async def send_system_alert(
        self,
        title: str,
        error_message: str,
        details: Optional[str] = None,
        task_id: str = "default",
    ) -> bool:
        """Envoie un Embed d'alerte rouge en DM privé avec boutons d'action (Relancer / Voir les logs)."""
        if not self._client:
            return False
        try:
            resp = await self._client.post(
                "/alert",
                json={
                    "title": title,
                    "error_message": error_message,
                    "details": details,
                    "task_id": task_id,
                },
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error("[discord-js] Échec envoi alerte système : %s", e)
            return False

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
        if not self._client:
            return False
        try:
            resp = await self._client.post(
                "/tool_progress",
                json={
                    "chat_id": chat_id,
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "status": status,
                    "output": output,
                    "is_final": is_final,
                },
            )
            return resp.status_code == 200
        except Exception:
            return False

    async def send_exec_approval(
        self,
        chat_id: str,
        command: str,
        description: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> SendResult:
        """Affiche les boutons d'approbation interactive pour une commande sensible."""
        if not self._client:
            return SendResult(success=False, error="Client non initialisé")
        try:
            resp = await self._client.post(
                "/exec_approval",
                json={
                    "chat_id": chat_id,
                    "command": command,
                    "description": description,
                    "reply_to": reply_to,
                },
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("success"):
                return SendResult(success=True, message_id=data.get("message_id"))
            return SendResult(success=False, error=data.get("error", "Erreur"))
        except Exception as e:
            return SendResult(success=False, error=str(e))

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
        """Pose une question interactive avec rendu riche style pi-bridge (menus déroulants, modales, etc.)."""
        if not self._client:
            return {"status": "cancelled", "answers": [], "error": "Client non initialisé"}
        try:
            resp = await self._client.post(
                "/ask",
                json={
                    "chat_id": chat_id,
                    "question": question,
                    "options": options or [],
                    "details": details,
                    "context": context,
                    "multiSelect": multi_select,
                    "timeoutSeconds": timeout_seconds,
                    "reply_to": reply_to,
                },
                timeout=timeout_seconds + 5 if timeout_seconds else None,
            )
            return resp.json()
        except Exception as e:
            logger.error("[discord-js] Échec lors de la question interactive : %s", e)
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
        """Affiche les options de clarification/question style pi-bridge pour répondre en un clic ou saisir du texte."""
        if not self._client:
            return SendResult(success=False, error="Client non initialisé")
        try:
            resp = await self._client.post(
                "/clarify",
                json={
                    "chat_id": chat_id,
                    "question": question,
                    "options": options,
                    "reply_to": reply_to,
                    "details": details,
                    "context": context,
                    "multiSelect": multi_select,
                    "timeoutSeconds": timeout_seconds,
                },
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("success"):
                return SendResult(success=True, message_id=data.get("message_id"))
            return SendResult(success=False, error=data.get("error", "Erreur"))
        except Exception as e:
            return SendResult(success=False, error=str(e))

    async def send_typing(self, chat_id: str) -> None:
        """Envoie l'indicateur d'écriture via le sidecar."""
        if not self._client:
            return
        try:
            await self._client.post("/typing", json={"chat_id": chat_id})
        except Exception:
            pass

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Récupère les métadonnées d'un salon via le sidecar."""
        if not self._client:
            return {"name": "unknown", "type": "unknown", "chat_id": chat_id}
        try:
            resp = await self._client.get("/chat_info", params={"chat_id": chat_id})
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {"name": "unknown", "type": "unknown", "chat_id": chat_id}

    async def disconnect(self) -> None:
        """Arrête proprement le sidecar et les tâches en arrière-plan."""
        self._mark_disconnected()
        if self._inbound_task:
            self._inbound_task.cancel()
            self._inbound_task = None

        if self._client:
            await self._client.aclose()
            self._client = None

        if self._proc and self._proc.poll() is None:
            logger.info("[discord-js] Arrêt du processus sidecar...")
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None


def register(ctx) -> None:
    """Point d'entrée du plugin appelé par le système de découverte d'Hermes Agent."""
    # Enregistre sous "discord" pour remplacer l'adaptateur discord.py built-in
    ctx.register_platform(
        name="discord",
        label="Discord (discord.js fine-tuned)",
        adapter_factory=lambda cfg: DiscordJsAdapter(cfg),
        check_fn=check_requirements,
        required_env=["DISCORD_BOT_TOKEN"],
        allowed_users_env="DISCORD_ALLOWED_USERS",
        allow_all_env="DISCORD_ALLOW_ALL_USERS",
        cron_deliver_env_var="DISCORD_HOME_CHANNEL",
        max_message_length=2000,
        emoji="💬",
        allow_update_command=True,
    )
    # Enregistre également sous "discord-js" pour compatibilité
    ctx.register_platform(
        name="discord-js",
        label="Discord.js (fine-tuned)",
        adapter_factory=lambda cfg: DiscordJsAdapter(cfg),
        check_fn=check_requirements,
        required_env=["DISCORD_BOT_TOKEN"],
        allowed_users_env="DISCORD_ALLOWED_USERS",
        allow_all_env="DISCORD_ALLOW_ALL_USERS",
        cron_deliver_env_var="DISCORD_HOME_CHANNEL",
        max_message_length=2000,
        emoji="💬",
        allow_update_command=True,
    )
