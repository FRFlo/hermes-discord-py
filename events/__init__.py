"""Gestionnaires d'événements Discord."""

from .lifecycle import handle_message_delete, handle_message_edit

__all__ = ["handle_message_delete", "handle_message_edit"]
