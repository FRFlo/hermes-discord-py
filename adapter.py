"""Adaptateur de plateforme Discord.js pour Hermes Agent.

Fait le pont entre Hermes Agent et un processus sidecar Node.js exécutant discord.js.
Les messages entrants transitent via un flux SSE sur la boucle locale (GET /inbound).
Les messages sortants et actions transitent via des requêtes HTTP POST locales.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

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
    """Adaptateur de plateforme reliant Hermes à un sidecar Node.js discord.js."""

    def __init__(self, config: PlatformConfig):
        # Initialise BasePlatformAdapter avec l'identifiant personnalisé de plateforme
        super().__init__(config, Platform("discord-js"))
        self._port = int(os.environ.get("HERMES_DISCORD_JS_PORT", _DEFAULT_SIDECAR_PORT))
        self._token = secrets.token_hex(16)
        self._proc: Optional[subprocess.Popen] = None
        self._inbound_task: Optional[asyncio.Task] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._bot_token = os.environ.get("DISCORD_BOT_TOKEN", "")

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
            logger.warning("[discord-js] npm non trouvé ; installation automatique des dépendances ignorée")
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
            logger.error("[discord-js] Impossible de démarrer le sidecar : Node.js n'est pas installé ou introuvable.")
            return False

        self._ensure_sidecar_deps()

        env = os.environ.copy()
        env["HERMES_SIDECAR_PORT"] = str(self._port)
        env["HERMES_SIDECAR_TOKEN"] = self._token
        if self._bot_token:
            env["DISCORD_BOT_TOKEN"] = self._bot_token

        # Vérifie si le fichier compilé dist/index.js existe, sinon utilise tsx
        dist_entry = _SIDECAR_DIR / "dist" / "index.js"
        src_entry = _SIDECAR_DIR / "src" / "index.ts"

        if dist_entry.exists():
            cmd = [node, str(dist_entry)]
        else:
            npx = shutil.which("npx") or "npx"
            cmd = [npx, "tsx", str(src_entry)]

        logger.info("[discord-js] Lancement du processus sidecar : %s", " ".join(cmd))
        self._proc = subprocess.Popen(
            cmd,
            cwd=str(_SIDECAR_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self._client = httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=30.0)

        # Attente de la disponibilité via /healthz
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
            logger.error("[discord-js] Délai dépassé lors du contrôle de santé (health check) du sidecar.")
            self._proc.kill()
            return False

        self._inbound_task = asyncio.create_task(self._listen_inbound())
        self._mark_connected()
        logger.info("[discord-js] Sidecar connecté et opérationnel sur le port %d", self._port)
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
        """Convertit l'événement JSON du sidecar en MessageEvent Hermes."""
        chat_id = str(data.get("chat_id", ""))
        sender_id = str(data.get("sender_id", ""))
        content = str(data.get("content", ""))
        message_id = str(data.get("message_id", ""))
        is_dm = bool(data.get("is_dm", False))

        source = self.build_source(
            chat_id=chat_id,
            user_id=sender_id,
            user_name=data.get("sender_name", ""),
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

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Envoie un message texte via le sidecar."""
        if not self._client:
            return SendResult(success=False, error="Client sidecar non initialisé")

        try:
            resp = await self._client.post(
                "/send",
                json={
                    "chat_id": chat_id,
                    "content": content,
                    "reply_to": reply_to,
                    "metadata": metadata or {},
                },
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("success"):
                return SendResult(success=True, message_id=data.get("message_id"))
            return SendResult(success=False, error=data.get("error", "Erreur inconnue"))
        except Exception as e:
            logger.error("[discord-js] Échec lors de l'envoi du message : %s", e)
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
    ctx.register_platform(
        name="discord-js",
        label="Discord (discord.js)",
        adapter_factory=lambda cfg: DiscordJsAdapter(cfg),
        check_fn=check_requirements,
        required_env=["DISCORD_BOT_TOKEN"],
        allowed_users_env="DISCORD_ALLOWED_USERS",
        allow_all_env="DISCORD_ALLOW_ALL_USERS",
        cron_deliver_env_var="DISCORD_HOME_CHANNEL",
        max_message_length=2000,
        emoji="🤖",
        allow_update_command=True,
    )
