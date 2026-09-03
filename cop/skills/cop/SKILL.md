---
name: cop
description: Delegate a coding task to a GitHub Copilot CLI agent running in a Herdr pane, and collect the result asynchronously, using the cop CLI. Use when the user asks to hand off/delegate a task to Copilot, run something in the background via Copilot, or mentions "cop start", "cop collect", or delegating work to a Copilot agent.
updated: 2026-09-02
---

# cop - delegate tasks to GitHub Copilot CLI agents

**If this skill was invoked as `/cop <task>`: the arguments name the task to
delegate. Do not research, plan, or answer it yourself — your only job is to hand it
off.** The Copilot agent starts with none of this conversation's context, so don't
pass `<arguments>` through verbatim if it's a fragment that only makes sense here
(e.g. "fix the bug we discussed", "do that refactor") -- rewrite it into a
self-contained task using whatever you already know (the file/function/error in
question, the repo, constraints mentioned earlier). If the arguments are already
self-contained, pass them through as-is; don't pad out a task that's already clear.
Then run `cop start "<task>" --dir <target repo> --name <short-mnemonic-slug>`
(default `--dir` to the current working directory's repo unless the user names
another; pick `--name` from the task itself, e.g. "add-foo-tests"), and report the
job id back. If the rewritten task is long (multi-paragraph, includes pasted code or
logs), pipe it via stdin instead of a shell argument -- `cop start --dir <target
repo> --name <slug> <<'EOF' ... EOF` -- rather than fighting shell quoting on a huge
`"<task>"` string. This applies even if you think you already know the answer, or the task
looks small enough to just do directly — delegating it to Copilot is the point of
`/cop`, every time. Everything below is reference for the underlying `cop` CLI, used
both for that handoff and whenever the user asks about `cop`/Copilot delegation
directly.

Don't spend a turn pre-checking the environment first (`which herdr`, `echo
$HERDR_ENV`, `cop --version`, etc.) -- just run `cop start` directly. It already
fails fast with a clear error if `HERDR_ENV`/`herdr`/`copilot` aren't set up, so a
separate check only adds latency without changing what you'd do next.

Hands a task to a fresh `copilot` agent in its own Herdr pane and lets you collect the
result later instead of blocking. Requires running inside a Herdr-managed pane
(`HERDR_ENV=1`), with `herdr` and `copilot` on `PATH`. Run `cop <command> --help` for
full flags; `--json` works on every command. Full docs:
https://github.com/vivainio/cop-pilot

```bash
cop start "Add unit tests for src/foo.py" --dir ~/r/myrepo
# -> prints a job id immediately; the agent keeps working in its own pane

cop collect <job-id> --wait
# -> blocks until the agent settles, then prints/stores its response
```

Other commands: `cop respond <job-id> "<text>"` (answer a prompt that left a job
`blocked`), `cop show <job-id>`, `cop list`, `cop status`.

Pass `--worktree` to `start` when the target repo already has other work sitting in it
(uncommitted changes, another agent running there) — it runs the task in a fresh git
worktree (via `herdr worktree create`) instead of `--dir` directly, so the agent can't
collide with that other work. It shows up as its own workspace in herdr and its own
branch named after the agent; remove it later with `herdr worktree remove` (the user
can also do this from the herdr UI).

## Gotchas

- `start` never blocks on the task finishing. Don't run `cop collect <job-id> --wait`
  as a normal blocking tool call either — the Copilot agent can take a while, and that
  ties up your own turn for the whole duration. Run it via Bash with
  `run_in_background: true` (or a Monitor loop) so you're notified when it settles
  instead of blocking on it.
- `blocked` status means the agent is waiting on an in-pane prompt; unblock with
  `cop respond <job-id> "<answer>"`, then `collect` again.
- A long response can get truncated by the pane read — if so, ask the task (via
  `respond`) to write its answer to a file and reply with just the path.
