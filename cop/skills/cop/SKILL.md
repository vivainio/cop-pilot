---
name: cop
description: Delegate a coding task to a GitHub Copilot CLI agent running in a Herdr pane, and collect the result asynchronously, using the cop CLI. Use when the user asks to hand off/delegate a task to Copilot, run something in the background via Copilot, or mentions "cop start", "cop collect", or delegating work to a Copilot agent.
updated: 2026-09-02
---

# cop - delegate tasks to GitHub Copilot CLI agents

Hands a coding task to a fresh `copilot` agent running in its own Herdr pane, and lets
you collect the result later instead of blocking on it. See
https://github.com/vivainio/cop-pilot for full docs.

**Requires:** running inside a Herdr-managed pane (`HERDR_ENV=1` set), with `herdr`
and `copilot` on `PATH`.

## Core flow

```bash
cop start "Add unit tests for src/foo.py" --dir ~/r/myrepo
# -> prints a job id immediately; the Copilot agent keeps working in its own pane
# (task can also come from stdin for a quick throwaway job:
#  echo "fix the typo in README" | cop start --dir ~/r/myrepo)

# ... do other things, or poll ...

cop collect <job-id> --wait
# -> blocks until the agent settles, then prints/stores its response
```

## Commands

```bash
cop start [<task>] --dir <path> [--name <mnemonic>] [--json]
# Opens a new tab in a dedicated cop-tasks Herdr workspace, starts a copilot agent
# there, sends the task, and returns a job id as soon as the agent confirms it
# started working. Does NOT wait for the task to finish.

cop collect <job-id> [--wait] [--timeout MS] [--raw] [--json]
# Without --wait: non-blocking status check.
# With --wait: blocks until the agent reaches idle/done/blocked, then reads back
# its result. --raw returns the full pane dump instead of just the last turn.

cop respond <job-id> "<text>" [--wait] [--raw] [--json]
# Send a follow-up into a job's agent, e.g. to answer a permission/approval
# prompt that left it "blocked".

cop show <job-id> [--refresh] [--json]
# Full detail for one job.

cop list [--json]
# Table of all known jobs, cached status (no herdr calls, works offline).

cop status [--json]
# Table of all known jobs, refreshing every non-terminal job's live status first.
```

Every command accepts `--json` for machine-readable output. Jobs are flat JSON files
under `~/.cop/jobs` (override with `COP_HOME`).

## Usage notes

- `start` is fire-and-forget: it returns as soon as the agent confirms it started, not
  when the task finishes. Always follow up with `cop collect <job-id> --wait` (or poll
  without `--wait`) to get the result.
- If `collect` reports the job as `blocked`, the agent is waiting on a prompt inside
  its pane — use `cop respond <job-id> "<answer>"` to unblock it, then `collect`
  again.
- A very long response can be truncated by the pane read. If that happens, ask the
  task (via `respond`) to write its full answer to a file and reply with just the
  path, then read that file directly.
- One job = one fresh Copilot session; there's no session reuse across `start` calls.
