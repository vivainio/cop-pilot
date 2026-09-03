# cop

Delegate coding tasks to a [GitHub Copilot CLI](https://docs.github.com/copilot/how-tos/set-up/install-copilot-cli)
agent running in a [Herdr](https://herdr.dev) pane, and collect the result later.

Typical use: Claude Code is your daily driver, but cheap/parallelizable
subtasks get farmed out to Copilot running the **Luna** model
(`gpt-5.6-luna`) — Luna is cheaper *and* noticeably sharper than Haiku, so it
beats reaching for Haiku as your low-cost delegate:

```
cop start "Add unit tests for src/foo.py" --dir ~/r/myrepo --model gpt-5.6-luna
```

## Install

```
uv tool install cop-pilot
# or: pip install cop-pilot
# or: uv tool install git+https://github.com/vivainio/cop-pilot
```

Requires: running inside a Herdr-managed pane (`HERDR_ENV=1`); `herdr` and
`copilot` on `PATH`.

## Usage

```
cop start "Add unit tests for src/foo.py" --dir ~/r/myrepo
# -> prints a job id immediately, agent keeps working in its own pane

echo "fix the typo in README" | cop start --dir ~/r/myrepo
# task from stdin

cop collect <job-id> --wait
# -> blocks until the agent settles, prints/stores its response

cop respond <job-id> "yes, proceed"
# answer a permission/approval prompt that left the job blocked

cop show <job-id>          # full detail for one job
cop list                   # all known jobs, cached status (offline)
cop status                 # all known jobs, refreshed from herdr
```

`cop start [<task>] --dir <path> [--name <mnemonic>] [--model <id>]` — agent
is named `cop-<name-or-dirname>`, falling back to appending the job id if
that name is taken. `--model` is passed through to `copilot --model <id>`;
omit it and copilot falls back to whatever's set as the default model in
`~/.copilot/settings.json` (`"model": "..."`, set via the `/model` slash
command in an interactive `copilot` session). Every job gets its own herdr
workspace, labeled with its agent name so it's identifiable in the
workspace list. Add `--worktree` to also run it in a fresh git worktree
(branch `worktrees/<name>`) instead of `--dir` directly, so it can't
collide with other work already in that checkout.

`cop collect <job-id> [--wait] [--timeout MS] [--raw]` — without `--wait`,
non-blocking status check. `--raw` dumps the full pane instead of just the
last turn.

Every command accepts `--json`. Jobs are flat JSON files under `~/.cop/jobs`
(override with `COP_HOME`).

## Claude Code skill

```
cop install-skills                       # installs to ~/.claude/skills/
cop install-skills --skills-dir ./skills # custom target
```

With the skill installed, Claude Code drives `cop` itself when you delegate:

> **/cop** check this pre-commit hook script, does it need updating for the
> new CI runner: https://issues.example.com/browse/PROJ-1234
>
> Claude reworks the short ask into a self-contained task before handing it
> off — the delegate has no memory of this conversation:
>
> ```
> cop start "Review the repo's pre-commit hook script(s) against
> https://issues.example.com/browse/PROJ-1234 (CI runner is being upgraded).
> Determine whether the hook needs changes to keep working there, and if so
> propose the fix." --dir ~/r/myrepo
> ```
>
> Delegated. Job started: `504ce49b` (agent `cop-check-hook`, pane `w8K:p6`)
> in `~/r/myrepo`.
>
> Collecting in the background.

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

- Pane reads can truncate very long responses — ask the task (via `respond`)
  to write its answer to a file and reply with the path instead.
- No session reuse across jobs — each `start` begins a fresh Copilot session.
