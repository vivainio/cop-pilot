"""Get a clean answer out of a `codex` session.

Codex has no `--session-id`, so the session is found after the fact: it writes
`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`, whose first line is a
`session_meta` event carrying the session's cwd and start time. The final
answer is a `response_item` message with `phase: "final_answer"`.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

SESSIONS_DIR = Path.home() / ".codex" / "sessions"


def _meta(path: Path) -> dict | None:
    try:
        with path.open() as f:
            first = json.loads(f.readline())
    except (OSError, json.JSONDecodeError):
        return None
    return first.get("payload") if first.get("type") == "session_meta" else None


def find_session(cwd: str, since: str) -> Path | None:
    """Newest rollout file started in `cwd` at or after ISO time `since`."""
    start = datetime.fromisoformat(since)
    target = str(Path(cwd).resolve())
    best: tuple[datetime, Path] | None = None
    for path in SESSIONS_DIR.glob("*/*/*/rollout-*.jsonl"):
        meta = _meta(path)
        if not meta or str(Path(meta.get("cwd", "")).resolve()) != target:
            continue
        try:
            ts = datetime.fromisoformat(meta["timestamp"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if ts >= start and (best is None or ts > best[0]):
            best = (ts, path)
    return best[1] if best else None


def extract_final_answer(session_file: Path) -> str | None:
    """Last final_answer message in the rollout, or None if absent/unreadable."""
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
        p = event.get("payload", {})
        if (
            event.get("type") == "response_item"
            and p.get("type") == "message"
            and p.get("phase") == "final_answer"
        ):
            answer = "".join(c.get("text", "") for c in p.get("content", []))
    return answer
