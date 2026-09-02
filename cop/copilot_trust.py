"""Pre-seed GitHub Copilot CLI's folder-trust config.

On a directory it hasn't seen before, `copilot` shows an interactive
"Confirm folder trust" modal at startup -- before any prompt is sent, and
before the TUI is otherwise doing anything. Herdr's agent lifecycle
detection does not recognize this modal as `blocked`; it reports the pane
as `idle`/`interactive_ready`. No CLI flag suppresses it either (checked
--add-dir, --allow-all-tools, --allow-all). A prompt sent into it lands as
raw keystrokes on a list widget, not as text -- so it silently never reaches
a real chat turn.

The only way to skip it is to already be listed in `trustedFolders` in
~/.copilot/config.json (the same effect as answering "Yes, and remember
this folder for future sessions" once, by hand).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

CONFIG_PATH = Path.home() / ".copilot" / "config.json"


def is_trusted(directory: str) -> bool:
    if not CONFIG_PATH.exists():
        return False
    text = CONFIG_PATH.read_text()
    match = re.search(r'"trustedFolders"\s*:\s*\[(.*?)\]', text, re.DOTALL)
    if not match:
        return False
    entries = re.findall(r'"((?:[^"\\]|\\.)*)"', match.group(1))
    target = str(Path(directory))
    return any(str(Path(e)) == target for e in entries)


def trust(directory: str) -> bool:
    """Add `directory` to trustedFolders if it isn't already there.

    Edits the config file textually (not a JSON parse/re-dump) so unrelated
    content -- notably a live `copilotTokens` credential -- is left exactly
    as-is. Returns True if the file was changed.
    """
    if not CONFIG_PATH.exists() or is_trusted(directory):
        return False
    text = CONFIG_PATH.read_text()
    match = re.search(r'("trustedFolders"\s*:\s*\[)(.*?)(\])', text, re.DOTALL)
    if not match:
        return False
    body = match.group(2)
    entry = json.dumps(str(Path(directory)))
    if body.strip():
        prefix = body.rstrip()
        if not prefix.endswith(","):
            prefix += ","
        new_body = f"{prefix}\n    {entry}\n  "
    else:
        new_body = f"\n    {entry}\n  "
    new_text = (
        text[: match.start()]
        + match.group(1)
        + new_body
        + match.group(3)
        + text[match.end() :]
    )
    CONFIG_PATH.write_text(new_text)
    return True
