"""Thin subprocess wrapper around the `herdr` CLI."""

from __future__ import annotations

import json
import subprocess


class HerdrError(RuntimeError):
    def __init__(self, args: list[str], returncode: int, stderr: str) -> None:
        self.args_ran = args
        self.returncode = returncode
        self.stderr = stderr
        detail = stderr.strip()
        try:
            parsed = json.loads(detail)
            detail = parsed.get("error", parsed)
        except (json.JSONDecodeError, AttributeError):
            pass
        super().__init__(f"herdr {' '.join(args)} failed ({returncode}): {detail}")


def _exec(args: list[str]) -> str:
    proc = subprocess.run(
        ["herdr", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise HerdrError(args, proc.returncode, proc.stderr)
    return proc.stdout


def run(args: list[str]) -> dict:
    """Run `herdr <args>` and return the parsed JSON result payload."""
    stdout = _exec(args).strip()
    if not stdout:
        return {}
    payload = json.loads(stdout)
    return payload.get("result", payload)


def run_text(args: list[str]) -> str:
    """Run `herdr <args>` for a command that prints raw text (e.g. reads)."""
    return _exec(args)


def pane_split(*, cwd: str, direction: str = "right", no_focus: bool = True) -> str:
    args = ["pane", "split", "--current", "--direction", direction, "--cwd", cwd]
    args.append("--no-focus" if no_focus else "--focus")
    result = run(args)
    return result["pane"]["pane_id"]


def workspace_create(*, label: str, cwd: str, no_focus: bool = True) -> dict:
    args = ["workspace", "create", "--label", label, "--cwd", cwd]
    args.append("--no-focus" if no_focus else "--focus")
    return run(args)


def worktree_create(
    *,
    cwd: str,
    branch: str,
    label: str,
    base: str | None = None,
    no_focus: bool = True,
) -> dict:
    """Create a Git worktree checkout (its own herdr workspace/tab/pane) off
    `cwd`'s repo. `base`, if given, is the ref the new `branch` starts from
    (herdr's own default is otherwise whatever `git worktree add` defaults
    to for `cwd`, typically its current HEAD). Returns the full
    `worktree_created` payload -- callers want `result["worktree"]["path"]`
    for the checkout dir and `result["root_pane"]["pane_id"]` for where to
    start the agent.
    """
    args = ["worktree", "create", "--cwd", cwd, "--branch", branch, "--label", label]
    if base:
        args += ["--base", base]
    args.append("--no-focus" if no_focus else "--focus")
    return run(args)


def agent_start(
    name: str,
    kind: str,
    pane_id: str,
    timeout_ms: int | None = None,
    extra_args: list[str] | None = None,
) -> dict:
    args = ["agent", "start", name, "--kind", kind, "--pane", pane_id]
    if timeout_ms is not None:
        args += ["--timeout", str(timeout_ms)]
    if extra_args:
        args += ["--", *extra_args]
    return run(args)


def agent_prompt(
    target: str,
    text: str,
    *,
    wait: bool = False,
    until: list[str] | None = None,
    timeout_ms: int | None = None,
) -> dict:
    args = ["agent", "prompt", target, text]
    if wait:
        args.append("--wait")
    for state in until or []:
        args += ["--until", state]
    if timeout_ms is not None:
        args += ["--timeout", str(timeout_ms)]
    return run(args)


def agent_wait(
    target: str,
    *,
    until: list[str] | None = None,
    timeout_ms: int | None = None,
) -> dict:
    args = ["agent", "wait", target]
    for state in until or []:
        args += ["--until", state]
    if timeout_ms is not None:
        args += ["--timeout", str(timeout_ms)]
    return run(args)


def agent_get(target: str) -> dict:
    return run(["agent", "get", target])


def agent_read(
    target: str,
    *,
    source: str = "recent-unwrapped",
    lines: int = 400,
    fmt: str = "text",
) -> str:
    return run_text(
        [
            "agent",
            "read",
            target,
            "--source",
            source,
            "--lines",
            str(lines),
            "--format",
            fmt,
        ]
    )


def agent_list() -> list[dict]:
    return run(["agent", "list"]).get("agents", [])


def agent_send_keys(target: str, *keys: str) -> dict:
    return run(["agent", "send-keys", target, *keys])
