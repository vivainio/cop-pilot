"""Extract the useful part of a `copilot` TUI pane read.

A pane read is a full-screen dump: a startup banner, a nav bar, "Tip"
boxes, the echoed prompt in its own bordered box, then the actual turn
(tool calls and the response), then a status bar and an empty input box.
Only that middle turn is ever wanted -- this strips the rest.
"""

from __future__ import annotations

import re
from pathlib import Path

# The echoed-prompt box's bottom border: a line of nothing but box-drawing
# "▀". The turn content starts right after the *last* one of these, so a
# multi-turn read (more history than just the last exchange) still isolates
# the most recent turn.
_PROMPT_BOX_END = re.compile(r"^\s*▀+\s*$", re.MULTILINE)

# The status bar always contains "Session: <n> AIC used"; the turn content
# ends right before it.
_STATUS_BAR = re.compile(r"Session:\s*[\d.]+\s*AIC used")

_SESSION_STATE_DIR = Path.home() / ".copilot" / "session-state"


def session_events_path(session_id: str) -> Path:
    """Path to the full structured event log (JSONL) for a `--session-id`
    Copilot was started with -- one JSON object per line: session start,
    model changes, tool calls, messages. The extracted/raw pane read only
    ever shows the last turn; this has the whole session, queryable, for
    when that isn't enough."""
    return _SESSION_STATE_DIR / session_id / "events.jsonl"


def extract_answer(raw: str) -> str:
    """Return just the last turn's content, or `raw` unchanged if the
    expected markers aren't found (e.g. a startup dialog, a non-copilot
    agent, or a Copilot UI change)."""
    prompt_ends = list(_PROMPT_BOX_END.finditer(raw))
    if not prompt_ends:
        return raw.strip()

    start = prompt_ends[-1].end()
    # Search from `start` onward -- a multi-turn read has one status bar per
    # turn, and only the one following the last turn marks its end.
    status = _STATUS_BAR.search(raw, start)
    if status:
        # Cut at the start of the status bar's *line*, not the "Session:"
        # substring's offset -- that line also has a cwd/branch prefix
        # before "Session:" which must be dropped too.
        line_start = raw.rfind("\n", 0, status.start())
        end = line_start if line_start != -1 else 0
    else:
        end = len(raw)

    lines = raw[start:end].splitlines()
    lines = [line.rstrip() for line in lines]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)
