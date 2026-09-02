"""Get a clean answer out of a `copilot` session.

Copilot writes a full structured JSONL event log per `--session-id` to
`~/.copilot/session-state/<session-id>/events.jsonl`. The final answer of a
turn is an `assistant.message` event with `phase: "final_answer"` and a
plain `content` string -- no banner, no box-drawing, nothing to parse
around. That's tried first.

Falls back to regex-stripping a raw Herdr pane read (banner, nav bar, tips,
the echoed prompt in its own box, then the actual turn, then a status bar
and an empty input box -- only that middle turn is wanted) for when the
session file is missing, unparseable, or has no final answer yet.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_SESSION_STATE_DIR = Path.home() / ".copilot" / "session-state"


def session_events_path(session_id: str) -> Path:
    """Path to the full structured event log (JSONL) for a `--session-id`
    Copilot was started with -- one JSON object per line: session start,
    model changes, tool calls, messages. Has the whole session, queryable,
    for anything a single extracted answer can't show."""
    return _SESSION_STATE_DIR / session_id / "events.jsonl"


def extract_final_answer(session_file: Path) -> str | None:
    """The most recently completed turn's answer, straight from the
    session's own event log. None if the file is missing, unparseable, or
    has no final_answer message yet (still working, or blocked mid-turn)."""
    try:
        lines = session_file.read_text().splitlines()
    except OSError:
        return None

    answer = None
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        data = event.get("data", {})
        if (
            event.get("type") == "assistant.message"
            and data.get("phase") == "final_answer"
        ):
            answer = data.get("content")
    return answer


# The echoed-prompt box's bottom border: a line of nothing but box-drawing
# "▀". The turn content starts right after the *last* one of these, so a
# multi-turn read (more history than just the last exchange) still isolates
# the most recent turn.
_PROMPT_BOX_END = re.compile(r"^\s*▀+\s*$", re.MULTILINE)

# The status bar always contains "Session: <n> AIC used"; the turn content
# ends right before it.
_STATUS_BAR = re.compile(r"Session:\s*[\d.]+\s*AIC used")


def extract_answer_from_pane(raw: str) -> str:
    """Fallback for when the session file isn't usable: return just the
    last turn's content from a raw pane read, or `raw` unchanged if the
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
