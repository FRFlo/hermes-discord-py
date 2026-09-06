"""Service de gestion des sessions Hermes et des fils de forum Discord."""

from __future__ import annotations

import datetime as dt
import inspect
import logging
from typing import Any, Dict, List, Optional

import discord

logger = logging.getLogger(__name__)


async def resolve_session_id(adapter: Any, chat_id: str, sender_id: str, is_dm: bool) -> Optional[str]:
    """Résout l'identifiant de session Hermes pour un salon Discord."""
    source = adapter.build_source(
        chat_id=chat_id,
        user_id=sender_id,
        user_name="User",
        chat_type="dm" if is_dm else "channel",
        chat_name="ForumSession",
    )
    if hasattr(adapter, "_session_store") and adapter._session_store:
        try:
            if hasattr(adapter._session_store, "get_or_create_session"):
                entry = adapter._session_store.get_or_create_session(source)
                if inspect.isawaitable(entry):
                    entry = await entry
                if entry and getattr(entry, "session_id", None):
                    return entry.session_id
        except Exception:
            pass
    try:
        from hermes_state import SessionDB
        db = SessionDB()
        finder = getattr(db, "find_session_by_origin", None)
        if callable(finder):
            sid = finder(platform="discord", chat_id=chat_id)
            if sid:
                return sid
    except Exception:
        pass
    return None


async def load_session_transcript(adapter: Any, session_id: str) -> List[Dict[str, Any]]:
    """Charge l'historique des messages d'une session Hermes."""
    if hasattr(adapter, "_session_store") and adapter._session_store:
        try:
            if hasattr(adapter._session_store, "load_transcript"):
                res = adapter._session_store.load_transcript(session_id)
                if inspect.isawaitable(res):
                    return await res
                return res
        except Exception:
            pass
    try:
        from hermes_state import SessionDB
        db = SessionDB()
        return db.get_messages(session_id, include_inactive=False)
    except Exception:
        return []


async def rewrite_session_transcript(adapter: Any, session_id: str, messages: List[Dict[str, Any]]) -> bool:
    """Réécrit l'historique des messages d'une session Hermes."""
    if hasattr(adapter, "_session_store") and adapter._session_store:
        try:
            if hasattr(adapter._session_store, "rewrite_transcript"):
                res = adapter._session_store.rewrite_transcript(session_id, messages, active_only=True)
                if inspect.isawaitable(res):
                    return await res
                return bool(res)
        except Exception:
            pass
    try:
        from hermes_state import SessionDB
        db = SessionDB()
        db.replace_messages(session_id, messages, active_only=True)
        return True
    except Exception:
        return False


async def purge_session(adapter: Any, chat_id: str) -> None:
    """Supprime une session dans SessionDB lors de la suppression d'un fil."""
    allowed = list(adapter._allowed_users)
    sender = allowed[0] if allowed else "0"
    session_id = await resolve_session_id(adapter, chat_id, sender, False)
    target = session_id or chat_id
    try:
        from hermes_state import SessionDB
        db = SessionDB()
        if hasattr(db, "delete_session"):
            db.delete_session(target)
            logger.info("[discord.session] Session %s supprimée de SessionDB", target)
    except Exception as e:
        logger.warning("[discord.session] Échec purge SessionDB %s : %s", target, e)


async def fetch_forum_threads(bot: discord.Client, forum_channel_id: Optional[str]) -> List[discord.Thread]:
    """Récupère les fils de discussion du salon forum configuré."""
    if not forum_channel_id:
        return []
    try:
        channel = await bot.fetch_channel(int(forum_channel_id))
        if isinstance(channel, discord.ForumChannel):
            active = await channel.threads()
            archived = [t async for t in channel.archived_threads(limit=20)]
            all_t = active + archived
            all_t.sort(key=lambda t: t.created_at or dt.datetime.min, reverse=True)
            return all_t[:25]
    except Exception as e:
        logger.debug("[discord.session] Échec fetch_forum_threads : %s", e)
    return []
