"""Plugin de plateforme Discord (discord.py fine-tuned) pour Hermes Agent."""

try:
    from .adapter import DiscordPyAdapter, register
except ImportError:
    from adapter import DiscordPyAdapter, register

__all__ = ["register", "DiscordPyAdapter"]
