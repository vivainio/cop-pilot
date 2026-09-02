# cop

Delegate coding tasks to a [GitHub Copilot CLI](https://docs.github.com/copilot/how-tos/set-up/install-copilot-cli)
agent running in a [Herdr](https://herdr.dev) pane, and collect the result later. `cop`
drives `herdr` directly (it's a plain subprocess call) — it doesn't need the `/herdr`
skill or any other intermediary to submit a task or collect its result; it's just as
happy called from a script or by hand as from a Claude session that happens to be
using the `/herdr` skill for other things.

The pattern is deliberately two steps, not one blocking call:

```
cop start "Add unit tests for src/foo.py" --dir ~/r/myrepo
# -> prints a job id immediately; the Copilot agent keeps working in its own pane
# (task can also come from stdin for a quick throwaway job, e.g.
#  echo "fix the typo in README" | cop start --dir ~/r/myrepo)

# ... do other things, or poll ...

cop collect <job-id> --wait
# -> blocks until the agent settles, then prints/stores its response
```

## Requirements

- Must run **inside a Herdr-managed pane** (`HERDR_ENV=1`) — it drives the `herdr` CLI
  directly over the local socket API.
- `herdr` and `copilot` (GitHub Copilot CLI) on `PATH`.

## Install

```
uv tool install git+https://github.com/<you>/cop
```

For local development:

```
uv sync
```

## Commands

- `cop start [<task>] --dir <path> [--name <mnemonic>]` — opens a new tab in a
  dedicated `cop-tasks` workspace (created on first use; unfocused, so it never
  steals the caller's view), starts a `copilot` agent there, sends the task, and
  returns a job id as soon as the agent confirms it started working (it does **not**
  wait for the task to finish). The agent is named `cop-<hint>`, where `<hint>` is
  `--name` if given, else the directory's name (e.g. `--name unit-tests` →
  `cop-unit-tests`) — readable in `herdr agent list` / Herdr's agents panel instead of
  a bare hex id. The job id is only appended (`cop-unit-tests-<job-id>`) if that plain
  name is already in use by another live agent. Trust and permission handling (see
  below) are unconditional. All delegated jobs land in that one workspace, one tab per
  job, so they never clutter whatever window/tab the caller is in. Herdr workspaces
  are flat (no parent/child relationship, confirmed via `herdr api schema`), so this
  can't be nested "under" the caller's own workspace the way a git worktree nests
  under its parent repo — a separate workspace is the closest available primitive.
- `cop collect <job-id> [--wait] [--timeout MS] [--raw]` — without `--wait`, does a
  non-blocking status check; with `--wait`, blocks until the agent reaches `idle`,
  `done`, or `blocked`, then reads back its terminal output as the result. By default
  the pane read is stripped down to just the last turn (see below); pass `--raw` for
  the full dump.
- `cop respond <job-id> "<text>" [--raw]` — send a follow-up into a job's agent, e.g.
  to answer a permission/approval dialog that left it `blocked`.
- `cop show <job-id> [--refresh]` — full detail for one job.
- `cop list` — table of all known jobs, cached status (no herdr calls, works offline).
- `cop status` — table of all known jobs, refreshing every non-terminal job's live
  status from herdr first.

Every command accepts `--json` for machine-readable output (useful when another agent
is the caller).

Jobs are flat JSON files under `~/.cop/jobs` (override with `COP_HOME`).

## Why `start` always does three things

Herdr's agent-lifecycle detection reports a Copilot pane as `idle`/ready-for-input
based on the screen looking settled — it has no idea what's actually on screen. Three
of Copilot's own startup/runtime screens look exactly like that to herdr, but aren't a
normal chat prompt, so a task sent into one of them silently goes nowhere (no error,
no state change, the job just never starts). `start` unconditionally works around
all three:

1. **Tool/approval prompts** — launches `copilot` with `--allow-all-tools
   --no-ask-user` so it never pauses for a permission or clarifying-question prompt.
   (Copilot's AI-judged `--assisted-approval` mode can't be used here — it's
   documented as prompt-mode (`-p`) only and refuses to start in the persistent
   interactive session herdr needs.)
2. **Folder trust** — a never-before-seen `--dir` shows an interactive "Confirm
   folder trust" dialog at startup, before anything else. No CLI flag suppresses it
   (checked `--add-dir`, `--allow-all-tools`, `--allow-all`) — the only way to skip it
   is to already be listed in Copilot's own `trustedFolders` config, so `start`
   pre-seeds `--dir` into `~/.copilot/config.json` (textually, leaving the rest of
   that file — including a live GitHub token — untouched).
3. **Session restore** — if a prior Copilot session in the same `--dir` was left
   "Interrupted" (e.g. its pane got closed mid-task), the next launch shows a
   "restore interrupted sessions" picker instead of a normal chat prompt. A fresh
   `--session-id` per job skips it.

`start` also confirms the prompt actually landed (waits for the agent to reach
`working`, retrying a couple of times on `agent_prompt_stalled`) instead of firing
blind — `agent_start` reporting ready can race a beat ahead of the TUI actually
accepting input.

## Result extraction and the full session log

`start` gives each job its own `--session-id`. Copilot writes a full structured event
log for it to `~/.copilot/session-state/<session-id>/events.jsonl` (one JSON object
per line: `session.start`, `user.message`, `model.response`, tool calls, ...) — shown
as `session_file` in every job. By default, `collect`/`respond` read the answer
straight from there: the last `assistant.message` event with `phase: "final_answer"`
has a plain `content` string, no chrome to parse around.

If the session file is missing, unparseable, or has no final answer yet (e.g. blocked
mid-turn), they fall back to scraping the pane — a full-screen dump (startup banner,
nav bar, tips, the echoed prompt in its own box, the turn, a status bar, an empty
input box) stripped down to just the last turn's content. Pass `--raw` to get that
raw pane dump directly, bypassing both.

`session_file` itself is worth keeping around regardless — it's the entire session,
queryable, for anything a single extracted answer can't show.

## Development

```
uv sync                    # install with dev dependencies
uv run pytest tests/ -v    # run tests
uv run ruff format .       # format
uv run ruff check .        # lint
uv run ty check            # type check
```

`hookmaster init .` installs a pre-commit hook (`githooks.toml`) that runs
`ruff format --check .`.

## Known limitations

- `agent read` only sees what's on Copilot's alternate screen / Herdr's scrollback of
  it; a very long response can be truncated. If that happens, ask the task (in a
  follow-up via `respond`) to write its full answer to a file and reply with just the
  path, then read the file directly.
- One job = one fresh pane + agent. There's no session reuse/continuation across jobs
  yet (each `start` begins a brand new Copilot session).
