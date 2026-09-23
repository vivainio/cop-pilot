"""Pre-seed Codex CLI's folder-trust config.

On an untrusted directory `codex` shows a "Do you trust this directory?"
modal at startup that herdr can't tell apart from a ready prompt, so a task
sent into it never lands. Listing the directory as
`[projects."<path>"] trust_level = "trusted"` in ~/.codex/config.toml skips it.
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".codex" / "config.toml"


def _header(directory: str) -> str:
    # A JSON string is a valid TOML basic string for the paths we deal with.
    return f"[projects.{json.dumps(str(Path(directory)))}]"


def is_trusted(directory: str) -> bool:
    if not CONFIG_PATH.exists():
        return False
    return _header(directory) in CONFIG_PATH.read_text()


def trust(directory: str) -> bool:
    """Append a trusted-project table if missing. Appends textually so the
    rest of the config (comments, credentials) is left exactly as-is.
    Returns True if the file was changed."""
    if not CONFIG_PATH.exists() or is_trusted(directory):
        return False
    text = CONFIG_PATH.read_text()
    sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    CONFIG_PATH.write_text(
        f'{text}{sep}{_header(directory)}\ntrust_level = "trusted"\n'
    )
    return True
