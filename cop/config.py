"""User config: which agent CLI `cop start` delegates to by default."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import jobs

AGENTS = ("copilot", "codex")


def _path() -> Path:
    return jobs.base_dir() / "config.json"


def load() -> dict:
    try:
        return json.loads(_path().read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def set_agent(agent: str) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**load(), "agent": agent}, indent=2) + "\n")


def resolve_agent(explicit: str | None = None) -> str:
    """--agent flag, else the configured default, else whichever single agent
    CLI is on PATH. Raises ValueError with a fix-it message otherwise."""
    if explicit:
        return explicit
    configured = load().get("agent")
    if configured in AGENTS:
        return configured
    installed = [a for a in AGENTS if shutil.which(a)]
    if len(installed) == 1:
        return installed[0]
    if not installed:
        raise ValueError(f"none of {', '.join(AGENTS)} found on PATH")
    raise ValueError(
        f"both {' and '.join(installed)} are installed -- pick a default "
        "with `cop init --agent <name>` (or pass --agent)"
    )
