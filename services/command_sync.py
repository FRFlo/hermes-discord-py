"""Public discord.py application-command synchronization."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from .. import adapter as _adapter

logger = _adapter.logger
_Path = Path
_DISCORD_COMMAND_SYNC_STATE_SUBDIR = _adapter._DISCORD_COMMAND_SYNC_STATE_SUBDIR
_DISCORD_COMMAND_SYNC_STATE_FILENAME = _adapter._DISCORD_COMMAND_SYNC_STATE_FILENAME
atomic_json_write = _adapter.atomic_json_write
_scoped_gate_env = lambda *args: _adapter._scoped_gate_env(*args)


class CommandSyncMixin:
    """Synchronize the command tree through ``discord.app_commands.CommandTree`` only."""

    def _command_sync_state_path(self) -> _Path:
        from hermes_constants import get_hermes_home

        directory = get_hermes_home() / _DISCORD_COMMAND_SYNC_STATE_SUBDIR
        directory.mkdir(parents=True, exist_ok=True)
        return directory / _DISCORD_COMMAND_SYNC_STATE_FILENAME

    def _read_command_sync_state(self) -> dict:
        try:
            data = json.loads(self._command_sync_state_path().read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _write_command_sync_state(self, state: dict) -> None:
        atomic_json_write(self._command_sync_state_path(), state, indent=None, separators=(",", ":"))

    def _desired_command_sync_fingerprint(self) -> str:
        tree = self._client.tree if self._client else None
        commands = [command.to_dict(tree) for command in tree.get_commands()] if tree else []
        payload = json.dumps(commands, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _get_discord_command_sync_policy(self) -> str:
        policy = _scoped_gate_env("DISCORD_COMMAND_SYNC_POLICY", "safe").lower()
        return policy if policy in {"off", "safe", "bulk"} else "safe"

    async def _run_post_connect_initialization(self) -> None:
        """Sync with the public ``CommandTree.sync`` API after gateway readiness."""
        if not self._client:
            return
        try:
            policy = self._get_discord_command_sync_policy()
            if policy == "off":
                logger.info("[%s] Skipping Discord slash command sync (policy=off)", self.name)
                return
            app_id = str(self._client.application_id or self._client.user.id)
            fingerprint = self._desired_command_sync_fingerprint()
            state = self._read_command_sync_state()
            previous = state.get(app_id, {})
            if policy == "safe" and previous.get("fingerprint") == fingerprint:
                logger.info("[%s] Skipping unchanged Discord slash command tree", self.name)
                return
            synced = await asyncio.wait_for(self._client.tree.sync(), timeout=60)
            state[app_id] = {"fingerprint": fingerprint, "synced_at": time.time(), "count": len(synced)}
            self._write_command_sync_state(state)
            logger.info("[%s] Synced %d Discord application command(s)", self.name, len(synced))
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning("[%s] Discord command sync failed: %s", self.name, error, exc_info=True)
