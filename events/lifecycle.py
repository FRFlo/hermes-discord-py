"""Gestion du cycle de vie des messages Discord (édition et suppression)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

try:
    from hermes_agent.gateway.platforms.base import MessageEvent, MessageType
except ImportError:
    import sys
    from pathlib import Path
    _HERMES_ROOT = Path("C:/Users/Flo/Desktop/hermes-agent")
    if str(_HERMES_ROOT) not in sys.path:
        sys.path.insert(0, str(_HERMES_ROOT))
    from gateway.platforms.base import MessageEvent, MessageType

from ..services.session_service import (
    load_session_transcript,
    resolve_session_id,
    rewrite_session_transcript,
)

logger = logging.getLogger(__name__)


async def handle_message_delete(
    adapter: Any,
    chat_id: str,
    message_id: str,
    sender_id: str,
    is_dm: bool,
) -> None:
    """Supprime le tour complet dans la session Hermes et nettoie les réponses sur Discord."""
    logger.info("[discord.events] Suppression détectée pour message_id=%s dans chat_id=%s", message_id, chat_id)

    # 1. Interruption immédiate si un travail tourne
    source = adapter.build_source(
        chat_id=chat_id,
        user_id=sender_id,
        user_name="System",
        chat_type="dm" if is_dm else "channel",
        chat_name="ForumSession",
        message_id=message_id,
    )
    try:
        await adapter.handle_message(MessageEvent(source=source, text="/stop", message_type=MessageType.COMMAND))
        await asyncio.sleep(0.2)
    except Exception:
        pass

    # 2. Résolution de la session Hermes
    session_id = await resolve_session_id(adapter, chat_id, sender_id, is_dm)
    if not session_id:
        return

    # 3. Chargement de l'historique
    transcript = await load_session_transcript(adapter, session_id)
    if not transcript:
        return

    target_idx = None
    target_role = None
    for i, entry in enumerate(transcript):
        mid = str(entry.get("message_id") or entry.get("platform_message_id") or "")
        if mid == message_id:
            target_idx = i
            target_role = entry.get("role")
            break

    if target_idx is None and message_id in adapter._bot_to_user_map:
        mapped_uid = adapter._bot_to_user_map[message_id]
        for i, entry in enumerate(transcript):
            mid = str(entry.get("message_id") or entry.get("platform_message_id") or "")
            if mid == mapped_uid:
                target_idx = i
                target_role = entry.get("role")
                break

    if target_idx is None:
        return

    # 4. Suppression selon le rôle
    if target_role == "assistant":
        new_transcript = [e for i, e in enumerate(transcript) if i != target_idx]
        await rewrite_session_transcript(adapter, session_id, new_transcript)
    else:
        # Message utilisateur : supprimer les réponses du bot sur Discord
        bot_reply_ids = adapter._reply_map.get(message_id, [])
        for b_id in bot_reply_ids:
            await adapter.delete_message(chat_id, b_id)
        adapter._reply_map.pop(message_id, None)

        # Supprimer de l'historique jusqu'au prochain message utilisateur
        turn_end = target_idx + 1
        while turn_end < len(transcript) and transcript[turn_end].get("role") != "user":
            turn_end += 1

        new_transcript = transcript[:target_idx] + transcript[turn_end:]
        await rewrite_session_transcript(adapter, session_id, new_transcript)


async def handle_message_edit(
    adapter: Any,
    chat_id: str,
    message_id: str,
    new_content: str,
    sender_id: str,
    sender_name: str,
    is_dm: bool,
) -> None:
    """Tronque l'historique de la session Hermes au message édité, nettoie Discord et relance la génération."""
    logger.info("[discord.events] Modification détectée pour message_id=%s dans chat_id=%s", message_id, chat_id)

    source = adapter.build_source(
        chat_id=chat_id,
        user_id=sender_id,
        user_name=sender_name,
        chat_type="dm" if is_dm else "channel",
        chat_name="ForumSession",
        message_id=message_id,
    )

    # 1. Interrompre toute tâche en cours
    try:
        await adapter.handle_message(MessageEvent(source=source, text="/stop", message_type=MessageType.COMMAND))
        await asyncio.sleep(0.2)
    except Exception:
        pass

    # 2. Résoudre la session
    session_id = await resolve_session_id(adapter, chat_id, sender_id, is_dm)
    if not session_id:
        return

    transcript = await load_session_transcript(adapter, session_id)
    if not transcript:
        return

    target_idx = None
    for i, entry in enumerate(transcript):
        mid = str(entry.get("message_id") or entry.get("platform_message_id") or "")
        if mid == message_id:
            target_idx = i
            break

    if target_idx is None:
        for i in range(len(transcript) - 1, -1, -1):
            if transcript[i].get("role") == "user":
                target_idx = i
                break

    if target_idx is None:
        return

    # 3. Supprimer l'ancienne réponse du bot sur Discord
    bot_reply_ids = adapter._reply_map.get(message_id, [])
    for b_id in bot_reply_ids:
        await adapter.delete_message(chat_id, b_id)
    adapter._reply_map.pop(message_id, None)

    # 4. Tronquer l'historique
    truncated = transcript[:target_idx]
    await rewrite_session_transcript(adapter, session_id, truncated)

    # 5. Relancer la génération avec le contenu mis à jour
    event = MessageEvent(
        source=source,
        text=new_content,
        message_type=MessageType.TEXT,
        raw_message={"message_id": message_id, "is_edit": True},
    )
    await adapter.handle_message(event)
