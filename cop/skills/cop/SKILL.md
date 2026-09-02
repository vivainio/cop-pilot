---
name: cop
description: Delegate a coding task to a GitHub Copilot CLI agent running in a Herdr pane, and collect the result asynchronously, using the cop CLI. Use when the user asks to hand off/delegate a task to Copilot, run something in the background via Copilot, or mentions "cop start", "cop collect", or delegating work to a Copilot agent.
updated: 2026-09-02
---

# cop - delegate tasks to GitHub Copilot CLI agents

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

## Gotchas

- `start` never blocks on the task finishing. Don't run `cop collect <job-id> --wait`
  as a normal blocking tool call either — the Copilot agent can take a while, and that
  ties up your own turn for the whole duration. Run it the way you'd wait on any other
  long shell command: in the background (or polled), so you're notified when it
  settles instead of blocking on it.
- `blocked` status means the agent is waiting on an in-pane prompt; unblock with
  `cop respond <job-id> "<answer>"`, then `collect` again.
- A long response can get truncated by the pane read — if so, ask the task (via
  `respond`) to write its answer to a file and reply with just the path.
