"""
Module de téléchargement et de mise en cache locale des pièces jointes Discord.
Télécharge les fichiers vers le répertoire configuré (HERMES_UPLOADS_DIR),
détecte les fichiers texte/code légers (< 50 Ko) et extrait leur contenu
pour auto-injection dans le contexte de l'agent.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {
    ".txt", ".md", ".json", ".yaml", ".yml", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".sh", ".bash", ".css", ".html", ".sql", ".env", ".toml", ".ini", ".conf",
    ".log", ".diff", ".patch", ".rs", ".go", ".c", ".cpp", ".h", ".hpp",
}

MAX_INJECT_SIZE_BYTES = 50 * 1024  # 50 Ko


@dataclass
class CachedAttachment:
    name: str
    url: str
    size: int
    local_path: str
    is_text: bool
    text_content: Optional[str] = None
    content_type: Optional[str] = None


def get_target_upload_dir() -> Path:
    """Résout et crée le répertoire de destination pour les pièces jointes."""
    candidates = [
        os.environ.get("HERMES_UPLOADS_DIR"),
        "/workspace/uploads",
        str(Path.cwd() / "cache" / "uploads"),
        str(Path.cwd() / "uploads"),
    ]
    for c in candidates:
        if not c:
            continue
        try:
            p = Path(c)
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            continue
    fallback = Path.cwd() / "uploads"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


async def download_and_cache_attachment(
    url: str,
    filename: str,
    size: int,
    content_type: Optional[str] = None,
    session: Optional[aiohttp.ClientSession] = None,
    uploads_dir: Optional[str] = None,
) -> CachedAttachment:
    """Télécharge une pièce jointe Discord, l'enregistre localement et extrait son texte si applicable."""
    upload_dir = Path(uploads_dir) if uploads_dir else get_target_upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
    target_path = upload_dir / f"{int(time.time())}_{safe_name}"

    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True

    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Échec téléchargement ({resp.status}) pour {url}")
            data = await resp.read()
            target_path.write_bytes(data)
    finally:
        if close_session:
            await session.close()

    ext = target_path.suffix.lower()
    is_text = ext in TEXT_EXTENSIONS or (bool(content_type and content_type.startswith("text/")))

    text_content: Optional[str] = None
    if is_text and target_path.stat().st_size <= MAX_INJECT_SIZE_BYTES:
        try:
            text_content = target_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning("Impossible d'extraire le texte de %s : %s", filename, e)

    return CachedAttachment(
        name=filename,
        url=url,
        size=target_path.stat().st_size if target_path.exists() else size,
        local_path=str(target_path),
        is_text=is_text,
        text_content=text_content,
        content_type=content_type,
    )
