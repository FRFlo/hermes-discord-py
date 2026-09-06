"""Service de gestion des tâches Cron Hermes pour l'adaptateur Discord."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def fetch_cron_jobs() -> List[Dict[str, Any]]:
    """Récupère la liste des tâches planifiées depuis Hermes."""
    try:
        from cron import jobs as cron_jobs
        if not cron_jobs:
            return []
        raw = cron_jobs.list_jobs(include_disabled=True)
        results = []
        for j in raw:
            results.append({
                "id": str(j.get("id", "")),
                "name": str(j.get("name") or (j.get("prompt", "")[:30] if j.get("prompt") else "Sans titre")),
                "schedule": str(j.get("schedule", "")),
                "schedule_display": str(j.get("schedule_display") or j.get("schedule", "")),
                "prompt": str(j.get("prompt", "")),
                "enabled": bool(j.get("enabled", True)),
                "last_run": j.get("last_run"),
                "last_status": j.get("last_status"),
                "next_run": j.get("next_run"),
                "deliver": str(j.get("deliver", "")),
            })
        return results
    except Exception as e:
        logger.debug("[discord.cron] Échec fetch_cron_jobs : %s", e)
        return []


async def handle_cron_action(action: str, job_id: str, chat_id: str) -> None:
    """Exécute une action sur une tâche Cron (pause, resume, trigger, delete)."""
    try:
        from cron import jobs as cron_jobs
    except ImportError:
        return

    if action == "pause":
        with asyncio.suppress(Exception):
            cron_jobs.pause_job(job_id)
    elif action == "resume":
        with asyncio.suppress(Exception):
            cron_jobs.resume_job(job_id)
    elif action == "trigger":
        with asyncio.suppress(Exception):
            if hasattr(cron_jobs, "trigger_job"):
                cron_jobs.trigger_job(job_id)
            elif hasattr(cron_jobs, "run_job"):
                cron_jobs.run_job(job_id)
    elif action == "delete":
        with asyncio.suppress(Exception):
            cron_jobs.remove_job(job_id)


async def handle_cron_create(name: str, schedule: str, prompt: str, deliver: str, chat_id: str) -> None:
    """Crée une nouvelle tâche cron dans Hermes."""
    try:
        from cron import jobs as cron_jobs
        if cron_jobs:
            cron_jobs.create_job(prompt=prompt, schedule=schedule, name=name, deliver=deliver or chat_id)
    except Exception as e:
        logger.warning("[discord.cron] Échec création tâche cron : %s", e)


def get_cron_last_output(job_id: str) -> Optional[str]:
    """Récupère le dernier rapport d'exécution sauvegardé pour une tâche cron."""
    try:
        from hermes_cli.config import get_hermes_home
        output_dir = Path(get_hermes_home()) / "cron" / "output" / job_id
        if output_dir.exists():
            files = sorted(output_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
            if files:
                return files[0].read_text(encoding="utf-8")[:1800]
    except Exception:
        pass
    return None
