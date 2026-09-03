"""cop: delegate coding tasks to a GitHub Copilot CLI agent running in a
Herdr pane, then collect the result once (or after) it finishes.

Typical flow:

    cop start "Add unit tests for src/foo.py" --dir ~/r/myrepo
    # -> prints a job id immediately; the copilot agent keeps working in its own pane
    ...
    cop collect <job-id> --wait
    # -> blocks until the agent settles, then prints/stores its response

State lives in flat JSON files under ~/.cop/jobs (override with COP_HOME).
This process must run inside a Herdr-managed pane (HERDR_ENV=1) since it
drives the herdr CLI directly.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import copilot_output, copilot_trust, herdr, jobs
from .skills import check_skill_staleness, install_skills_command

# Herdr agent lifecycle states -> job status. "unknown" and "working" pass through as-is.
_SETTLED = {"idle", "done"}

# Flags that put `copilot` into an unattended mode: --allow-all-tools skips
# tool-permission prompts and --no-ask-user stops it pausing to ask a
# clarifying question. (--assisted-approval, the AI-judged approval mode, is
# prompt-mode (-p) only -- it refuses to start in the persistent interactive
# session herdr needs for lifecycle tracking, so it can't be used here.)
_COPILOT_AUTO_ARGS = ["--allow-all-tools", "--no-ask-user"]

_NAME_RE = re.compile(r"[^a-z0-9_-]+")
_AGENT_PREFIX = "cop"


def _agent_name(hint: str, job_id: str, live_names: set[str]) -> str:
    """A name matching herdr's [a-z][a-z0-9_-]{0,31} agent-name pattern,
    readable enough to spot in `herdr agent list` -- e.g. "cop-unit-tests"
    rather than a bare hex id. `hint` is usually the repo's directory name,
    or a --name mnemonic when the caller wants something more memorable to
    search for. The job id is only appended when the plain name would
    collide with a currently-live agent.
    """
    base = _NAME_RE.sub("-", hint.lower()).strip("-")
    candidate = "-".join(p for p in (_AGENT_PREFIX, base) if p)[:32].strip("-")
    if candidate and candidate not in live_names:
        return candidate
    budget = 32 - len(_AGENT_PREFIX) - 2 - len(job_id)
    base = base[:budget].strip("-")
    return "-".join(p for p in (_AGENT_PREFIX, base, job_id) if p)


def _require_herdr_env() -> None:
    if os.environ.get("HERDR_ENV") != "1":
        print(
            "error: cop must run inside a Herdr-managed pane (HERDR_ENV=1 not set)",
            file=sys.stderr,
        )
        sys.exit(1)


# All delegated jobs live in one dedicated workspace (one tab per job) so
# they don't clutter whatever workspace/tab the caller is currently in.
# Herdr workspaces are flat/top-level (no parent-child relationship, per
# `herdr api schema`), so this can't be nested "under" the caller's own
# workspace the way a git worktree nests under its parent repo -- a
# separate workspace is the closest available primitive.
_WORKSPACE_LABEL = "cop-tasks"


def _ensure_workspace(cwd: str) -> str:
    for ws in herdr.workspace_list():
        if ws.get("label") == _WORKSPACE_LABEL:
            return ws["workspace_id"]
    created = herdr.workspace_create(label=_WORKSPACE_LABEL, cwd=cwd, no_focus=True)
    return created["workspace"]["workspace_id"]


def _agent_status(state: dict) -> str:
    """herdr agent get/wait/prompt all nest the live fields under "agent"."""
    return state.get("agent", state).get("agent_status", "unknown")


def _read_result(job: dict, target: str, *, lines: int, raw: bool) -> str:
    if raw:
        return herdr.agent_read(target, lines=lines)
    session_file = job.get("session_file")
    if session_file:
        answer = copilot_output.extract_final_answer(Path(session_file))
        if answer is not None:
            return answer
    # Session file missing/unparseable/no final answer yet (e.g. blocked
    # mid-turn) -- fall back to scraping the pane.
    return copilot_output.extract_answer_from_pane(
        herdr.agent_read(target, lines=lines)
    )


def _emit(data: dict, *, as_json: bool, text: str) -> None:
    if as_json:
        print(json.dumps(data, indent=2))
    else:
        print(text)


def cmd_start(args: argparse.Namespace) -> int:
    _require_herdr_env()
    task = args.task
    if task is None:
        if sys.stdin.isatty():
            print(
                "error: no task given (pass it as an argument or pipe it via stdin)",
                file=sys.stderr,
            )
            return 2
        task = sys.stdin.read().strip()
        if not task:
            print("error: empty task from stdin", file=sys.stderr)
            return 2

    directory = str(Path(args.dir).expanduser().resolve())
    job = jobs.new_job(task=task, directory=directory, kind="copilot")
    live_names = {a["name"] for a in herdr.agent_list() if a.get("name")}
    job["name"] = _agent_name(args.name or Path(directory).name, job["id"], live_names)
    job["worktree_path"] = None

    try:
        if args.worktree:
            # Own git worktree + its own herdr workspace, branched off
            # `directory`'s repo, so the agent can't collide with other work
            # already sitting in that checkout. `worktree create` returns a
            # ready-made pane, unlike the shared-workspace path below.
            created = herdr.worktree_create(
                cwd=directory,
                branch=f"worktrees/{job['name']}",
                label=job["name"],
                no_focus=True,
            )
            work_dir = created["worktree"]["path"]
            job["worktree_path"] = work_dir
            job["workspace_id"] = created["workspace"]["workspace_id"]
            job["tab_id"] = created["tab"]["tab_id"]
            pane_id = created["root_pane"]["pane_id"]
            job["pane_id"] = pane_id
        else:
            work_dir = directory
            workspace_id = _ensure_workspace(directory)
            tab = herdr.tab_create(
                workspace_id=workspace_id,
                cwd=directory,
                label=job["name"],
                no_focus=True,
            )
            pane_id = tab["root_pane"]["pane_id"]
            job["workspace_id"] = workspace_id
            job["tab_id"] = tab["tab"]["tab_id"]
            job["pane_id"] = pane_id
        jobs.save(job)

        # Pre-trust the repo so copilot's startup folder-trust dialog never
        # appears, and give it a brand-new session id so it never shows its
        # "restore interrupted sessions" picker either -- herdr can't tell
        # either of those modals apart from a settled, ready-for-input
        # screen, so a prompt sent into one silently goes nowhere.
        copilot_trust.trust(work_dir)
        session_id = str(uuid.uuid4())
        job["session_id"] = session_id
        job["session_file"] = str(copilot_output.session_events_path(session_id))
        extra_args = ["--session-id", session_id, *_COPILOT_AUTO_ARGS]
        if args.model:
            extra_args += ["--model", args.model]
            job["model"] = args.model
        herdr.agent_start(job["name"], "copilot", pane_id, extra_args=extra_args)
        # Confirm the prompt actually landed (agent transitioned to "working")
        # instead of firing blind -- a prompt sent moments after agent_start
        # can silently no-op if the TUI isn't fully settled yet. Retry a
        # couple of times on that specific stall; agent_start's readiness
        # check can fire a beat before the TUI truly accepts input.
        for attempt in range(3):
            try:
                herdr.agent_prompt(
                    job["name"],
                    task,
                    wait=True,
                    until=["working"],
                    timeout_ms=15000,
                )
                break
            except herdr.HerdrError as e:
                if "agent_prompt_stalled" not in str(e) or attempt == 2:
                    raise
                time.sleep(1.5)

        job["status"] = "working"
        jobs.save(job)
    except herdr.HerdrError as e:
        job["status"] = "error"
        job["error"] = str(e)
        jobs.save(job)
        _emit(
            {"id": job["id"], "status": "error", "error": str(e)},
            as_json=args.json,
            text=f"error: {e}\n(job {job['id']} recorded as failed; pane may be partially set up)",
        )
        return 1

    dir_line = (
        f"worktree: {job['worktree_path']}  (off {job['dir']})\n"
        if job.get("worktree_path")
        else f"dir:  {job['dir']}\n"
    )
    _emit(
        job,
        as_json=args.json,
        text=(
            f"started  job={job['id']}  agent={job['name']}  pane={job['pane_id']}\n"
            f"{dir_line}"
            f"task: {job['task']}\n"
            f"-> cop collect {job['id']} --wait"
        ),
    )
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    _require_herdr_env()
    try:
        job = jobs.load(args.job_id)
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    # "done" can also have been set by `status`/`show --refresh`, which only
    # check lifecycle state and never fetch the result -- only treat it as
    # already-collected if we actually have a result stored.
    already_collected = job["status"] == "error" or (
        job["status"] == "done" and job.get("result") is not None
    )
    if already_collected and not args.refresh:
        _emit(job, as_json=args.json, text=_format_job(job))
        return 0 if job["status"] == "done" else 1

    target = job["name"]
    try:
        if args.wait:
            state = herdr.agent_wait(target, timeout_ms=args.timeout)
        else:
            state = herdr.agent_get(target)
    except herdr.HerdrError as e:
        job["status"] = "error"
        job["error"] = str(e)
        jobs.save(job)
        _emit(
            {"id": job["id"], "status": "error", "error": str(e)},
            as_json=args.json,
            text=f"error: {e}",
        )
        return 1

    agent_status = _agent_status(state)

    if agent_status in _SETTLED:
        job["status"] = "done"
        job["result"] = _read_result(job, target, lines=args.lines, raw=args.raw)
    elif agent_status == "blocked":
        job["status"] = "blocked"
        job["result"] = _read_result(job, target, lines=args.lines, raw=args.raw)
    else:
        job["status"] = agent_status  # "working" or "unknown"

    jobs.save(job)
    _emit(job, as_json=args.json, text=_format_job(job))
    return 0 if job["status"] == "done" else (1 if job["status"] == "error" else 2)


def cmd_respond(args: argparse.Namespace) -> int:
    _require_herdr_env()
    try:
        job = jobs.load(args.job_id)
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    target = job["name"]
    try:
        if args.wait:
            herdr.agent_prompt(target, args.text, wait=True, timeout_ms=args.timeout)
        else:
            herdr.agent_prompt(target, args.text)
        state = herdr.agent_get(target)
    except herdr.HerdrError as e:
        job["status"] = "error"
        job["error"] = str(e)
        jobs.save(job)
        _emit(
            {"id": job["id"], "status": "error", "error": str(e)},
            as_json=args.json,
            text=f"error: {e}",
        )
        return 1

    agent_status = _agent_status(state)
    job["status"] = "done" if agent_status in _SETTLED else agent_status
    if job["status"] in ("done", "blocked"):
        job["result"] = _read_result(job, target, lines=args.lines, raw=args.raw)
    jobs.save(job)
    _emit(job, as_json=args.json, text=_format_job(job))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    try:
        job = jobs.load(args.job_id)
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if args.refresh:
        _require_herdr_env()
        try:
            state = herdr.agent_get(job["name"])
            job["status"] = _agent_status(state)
            jobs.save(job)
        except herdr.HerdrError:
            pass
    _emit(job, as_json=args.json, text=_format_job(job))
    return 0


def _humanize_age(iso_ts: str) -> str:
    try:
        then = datetime.fromisoformat(iso_ts)
    except ValueError:
        return iso_ts
    seconds = max(0, int((datetime.now(timezone.utc) - then).total_seconds()))
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 30:
        return f"{days}d ago"
    months = days // 30
    if months < 12:
        return f"{months}mo ago"
    return f"{days // 365}y ago"


def _result_size(job: dict) -> str:
    result = job.get("result")
    if not result:
        return "-"
    return f"{len(result) / 1024:.1f}kb"


def _print_job_table(all_jobs: list[dict]) -> None:
    if not all_jobs:
        print('no jobs yet -- run `cop start "<task>" --dir <path>`')
        return
    print(f"{'id':<10}{'status':<10}{'kind':<10}{'created':<12}{'size':<8}task")
    for job in all_jobs:
        task = job["task"].replace("\n", " ")
        if len(task) > 60:
            task = task[:57] + "..."
        age = _humanize_age(job["created_at"])
        size = _result_size(job)
        print(
            f"{job['id']:<10}{job['status']:<10}{job['kind']:<10}{age:<12}{size:<8}{task}"
        )


def cmd_list(args: argparse.Namespace) -> int:
    all_jobs = jobs.list_jobs()
    if args.json:
        print(json.dumps(all_jobs, indent=2))
        return 0
    _print_job_table(all_jobs)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Like `list`, but refreshes every non-terminal job's live agent status first."""
    _require_herdr_env()
    all_jobs = []
    for job in jobs.list_jobs():
        if job["status"] not in ("done", "error"):
            try:
                job["status"] = _agent_status(herdr.agent_get(job["name"]))
                jobs.save(job)
            except herdr.HerdrError:
                pass
        all_jobs.append(job)
    if args.json:
        print(json.dumps(all_jobs, indent=2))
        return 0
    _print_job_table(all_jobs)
    return 0


def _format_job(job: dict) -> str:
    lines = [
        f"job:    {job['id']}",
        f"status: {job['status']}",
        f"agent:  {job['name']}  pane={job.get('pane_id')} workspace={job.get('workspace_id')}",
        f"dir:    {job['dir']}",
    ]
    if job.get("worktree_path"):
        lines.append(f"worktree: {job['worktree_path']}")
    lines.append(f"task:   {job['task']}")
    if job.get("session_file"):
        lines.append(f"session: {job['session_file']}  (full structured event log)")
    if job.get("error"):
        lines.append(f"error:  {job['error']}")
    if job.get("result") is not None:
        lines.append("--- result " + "-" * 40)
        lines.append(job["result"])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("start", help="hand a task to a fresh Copilot agent pane")
    d.add_argument(
        "task",
        nargs="?",
        default=None,
        help="the task/prompt to send (reads stdin if omitted)",
    )
    d.add_argument(
        "--dir", default=".", help="working directory for the new pane (default: cwd)"
    )
    d.add_argument(
        "--name",
        default=None,
        help="mnemonic for the agent name (default: the directory name) -- "
        "makes it easier to spot in `herdr agent list`; the job id is only appended if that "
        "plain name is already in use",
    )
    d.add_argument(
        "--model",
        default=None,
        help="model for the Copilot agent to use, passed through as `copilot --model "
        "<id>` (e.g. gpt-5.6-luna); default is copilot's own default/last-used model",
    )
    d.add_argument(
        "--worktree",
        action="store_true",
        help="run in a fresh git worktree branched off --dir (via `herdr worktree "
        "create`) instead of --dir directly, so the agent can't collide with other "
        "work already sitting in that checkout; shows up as its own workspace in "
        "herdr and its own branch named after the agent -- remove it later with "
        "`herdr worktree remove`",
    )
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_start)

    c = sub.add_parser("collect", help="check on / fetch the result of a delegated job")
    c.add_argument("job_id")
    c.add_argument("--wait", action="store_true", help="block until the agent settles")
    c.add_argument("--timeout", type=int, default=None, help="ms, only with --wait")
    c.add_argument("--lines", type=int, default=400, help="pane lines to read back")
    c.add_argument(
        "--refresh", action="store_true", help="re-check even if already done/error"
    )
    c.add_argument(
        "--raw",
        action="store_true",
        help="store the full pane dump instead of just the extracted turn "
        "(banner/nav/echoed-prompt/status-bar stripped by default)",
    )
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_collect)

    r = sub.add_parser(
        "respond", help="send a follow-up (e.g. answer a blocked approval prompt)"
    )
    r.add_argument("job_id")
    r.add_argument("text")
    r.add_argument("--wait", action="store_true")
    r.add_argument("--timeout", type=int, default=None)
    r.add_argument("--lines", type=int, default=400)
    r.add_argument(
        "--raw", action="store_true", help="store the full pane dump, unextracted"
    )
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_respond)

    s = sub.add_parser("show", help="print full detail for one job")
    s.add_argument("job_id")
    s.add_argument(
        "--refresh", action="store_true", help="re-check live agent status first"
    )
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_show)

    ls = sub.add_parser("list", help="list all known jobs (cached status)")
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(func=cmd_list)

    st = sub.add_parser(
        "status", help="list all known jobs, refreshing live status first"
    )
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_status)

    isk = sub.add_parser(
        "install-skills",
        help="install the bundled Claude Code skill to $CLAUDE_CONFIG_DIR/skills/ (default: ~/.claude/skills/)",
    )
    isk.add_argument(
        "--skills-dir",
        default=None,
        help="target directory for the skill (default: $CLAUDE_CONFIG_DIR/skills/ or ~/.claude/skills/)",
    )
    isk.set_defaults(func=install_skills_command)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "install-skills":
        check_skill_staleness()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
