"""
Module de formatage et de découpage intelligent des messages pour Discord.
Gère le découpage Markdown respectant la limite de 2 000 caractères tout en préservant
l'intégrité des blocs de code, la conversion des réflexions IA en sous-texte Discord (-#),
et la sauvegarde des sorties volumineuses d'outils en fichiers attachés.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

MAX_DISCORD_LENGTH = 1950  # Marge de sécurité pour les balises de code et sauts de ligne

_THINKING_RE = re.compile(
    r"<(?:thinking|thought)>([\s\S]*?)<\/(?:thinking|thought)>",
    re.IGNORECASE,
)
_CODE_BLOCK_START_RE = re.compile(r"^```(\w*)")


def split_markdown(content: str, max_length: int = MAX_DISCORD_LENGTH) -> List[str]:
    """Découpe un message Markdown en plusieurs fragments respectant max_length,
    en fermant et réouvrant proprement les blocs de code Markdown."""
    if not content:
        return []
    if len(content) <= max_length:
        return [content]

    lines = content.split("\n")
    chunks: List[str] = []
    current_chunk = ""
    in_code_block = False
    code_block_lang = ""

    for line in lines:
        code_block_match = _CODE_BLOCK_START_RE.match(line)
        overhead = 4 if in_code_block else 0

        # Vérifie si l'ajout de cette ligne dépasse la limite
        if len(current_chunk) + len(line) + 1 + overhead > max_length:
            if current_chunk.strip():
                if in_code_block:
                    current_chunk += "\n```"
                    chunks.append(current_chunk)
                    current_chunk = f"```{code_block_lang}\n{line}"
                else:
                    chunks.append(current_chunk)
                    current_chunk = line
            else:
                # La ligne seule dépasse la limite max
                remaining = line
                while len(remaining) > max_length:
                    slice_len = max_length - (4 if in_code_block else 0)
                    part = remaining[:slice_len]
                    chunks.append(part + ("\n```" if in_code_block else ""))
                    remaining = (f"```{code_block_lang}\n" if in_code_block else "") + remaining[slice_len:]
                current_chunk = remaining
        else:
            if current_chunk:
                current_chunk += "\n" + line
            else:
                current_chunk = line

        if code_block_match:
            if in_code_block:
                in_code_block = False
                code_block_lang = ""
            else:
                in_code_block = True
                code_block_lang = code_block_match.group(1) or ""

    if current_chunk.strip():
        if in_code_block and not current_chunk.endswith("```"):
            current_chunk += "\n```"
        chunks.append(current_chunk)

    return chunks


def format_thinking_with_subtext(content: str) -> str:
    """Formate les blocs de réflexion interne (<thinking> ou <thought>)
    avec le format natif Discord de sous-texte (-# texte grisé et compact)."""
    if not content:
        return ""

    def _replace_thinking(match: re.Match) -> str:
        inner = match.group(1).strip()
        if not inner:
            return ""
        lines = inner.split("\n")
        subtext_lines = [f"-# {line}" for line in lines]
        return "\n".join(subtext_lines) + "\n\n"

    return _THINKING_RE.sub(_replace_thinking, content)


def save_large_output_to_log_file(
    tool_name: str,
    output: str,
    threshold: int = 1500,
    uploads_dir: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """Si la sortie d'un outil dépasse le seuil, l'enregistre dans un fichier .log ou .diff
    et retourne (résumé_écourté, chemin_fichier_local).
    Sinon retourne (output, None)."""
    if len(output) <= threshold:
        return output, None

    now = dt.datetime.now()
    time_str = now.strftime("%Hh%M_%S")
    ext = "diff" if "diff" in tool_name.lower() else "log"
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", tool_name)
    filename = f"{safe_name}_output_{time_str}.{ext}"

    target_dir_str = (
        uploads_dir
        or os.environ.get("HERMES_UPLOADS_DIR")
        or str(Path.cwd() / "uploads")
    )
    target_dir = Path(target_dir_str)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / filename
        file_path.write_text(output, encoding="utf-8")

        preview = output[:300].strip()
        summary = (
            f"{preview}...\n"
            f"*(Sortie complète de {len(output)} car. disponible dans le fichier joint `{filename}`)*"
        )
        return summary, str(file_path)
    except Exception:
        # En cas d'impossibilité d'écriture, découpage direct du texte
        return output[:threshold] + "\n...(tronqué)", None
