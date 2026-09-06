"""Enregistrement et configuration des commandes Slash Discord."""

from __future__ import annotations

from typing import Any

from discord import app_commands

from .control_cmds import register_control_commands
from .cron_cmds import register_cron_commands
from .model_cmds import register_model_commands
from .session_cmds import register_session_commands


def setup_all_commands(tree: app_commands.CommandTree, adapter: Any) -> None:
    """Enregistre l'ensemble des commandes slash de l'adaptateur sur le CommandTree."""
    register_control_commands(tree, adapter)
    register_session_commands(tree, adapter)
    register_model_commands(tree, adapter)
    register_cron_commands(tree, adapter)


__all__ = [
    "setup_all_commands",
    "register_control_commands",
    "register_session_commands",
    "register_model_commands",
    "register_cron_commands",
]
