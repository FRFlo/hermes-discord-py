"""Utilitaires et imports communs pour les vues Discord UI."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def truncate(text: str, max_len: int) -> str:
    """Tronque une chaîne si elle dépasse max_len."""
    if not text:
        return ""
    return text[: max_len - 3] + "..." if len(text) > max_len else text
