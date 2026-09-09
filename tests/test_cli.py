import argparse
import json
from datetime import datetime, timedelta, timezone
from typing import NoReturn

import pytest

from cop import herdr, jobs
from cop.cli import (
    _agent_name,
    _agent_status,
    _display_title,
    _humanize_age,
    _result_size,
    cmd_clear,
    cmd_collect,
)


def test_agent_name_uses_hint_when_available() -> None:
    assert _agent_name("myrepo", "deadbeef", live_names=set()) == "cop-myrepo"


def test_agent_name_sanitizes_hint() -> None:
    assert _agent_name("My Repo!!", "deadbeef", live_names=set()) == "cop-my-repo"


def test_agent_name_falls_back_to_job_id_on_collision() -> None:
    name = _agent_name("myrepo", "deadbeef", live_names={"cop-myrepo"})
    assert name == "cop-myrepo-deadbeef"


def test_agent_name_uses_bare_prefix_when_hint_sanitizes_to_empty() -> None:
    name = _agent_name("???", "deadbeef", live_names=set())
    assert name == "cop"


def test_agent_name_appends_job_id_when_bare_prefix_collides() -> None:
    name = _agent_name("???", "deadbeef", live_names={"cop"})
    assert name == "cop-deadbeef"


def test_agent_name_stays_within_length_limit() -> None:
    name = _agent_name("a" * 100, "deadbeef", live_names=set())
    assert len(name) <= 32


def test_agent_name_collision_fallback_stays_within_length_limit() -> None:
    hint = "a" * 100
    live = {_agent_name(hint, "deadbeef", live_names=set())}
    name = _agent_name(hint, "deadbeef", live_names=live)
    assert len(name) <= 32
    assert name.endswith("deadbeef")


def test_display_title_uses_first_nonblank_line() -> None:
    assert _display_title("\n  Add unit tests for src/foo.py  \n\nmore detail") == (
        "Add unit tests for src/foo.py"
    )


def test_display_title_truncates_long_task() -> None:
    task = "x" * 100
    title = _display_title(task)
    assert len(title) == 60
    assert title.endswith("…")


def test_display_title_empty_task_is_empty_string() -> None:
    assert _display_title("   \n  ") == ""


def test_agent_status_reads_nested_agent_field() -> None:
    state = {"agent": {"agent_status": "idle"}, "type": "agent_info"}
    assert _agent_status(state) == "idle"


def test_agent_status_defaults_to_unknown() -> None:
    assert _agent_status({}) == "unknown"


def _ago(**kwargs) -> str:
    return (datetime.now(timezone.utc) - timedelta(**kwargs)).isoformat(
        timespec="seconds"
    )


def test_humanize_age_just_now() -> None:
    assert _humanize_age(_ago(seconds=5)) == "just now"


def test_humanize_age_minutes() -> None:
    assert _humanize_age(_ago(minutes=5)) == "5m ago"


def test_humanize_age_hours() -> None:
    assert _humanize_age(_ago(hours=3)) == "3h ago"


def test_humanize_age_days() -> None:
    assert _humanize_age(_ago(days=2)) == "2d ago"


def test_humanize_age_months() -> None:
    assert _humanize_age(_ago(days=90)) == "3mo ago"


def test_humanize_age_years() -> None:
    assert _humanize_age(_ago(days=800)) == "2y ago"


def test_humanize_age_falls_back_on_bad_input() -> None:
    assert _humanize_age("not a timestamp") == "not a timestamp"


def test_result_size_missing_is_dash() -> None:
    assert _result_size({"result": None}) == "-"


def test_result_size_formats_kb() -> None:
    assert _result_size({"result": "a" * 2048}) == "2.0kb"


def test_collect_fetches_result_even_if_status_already_marked_done(monkeypatch) -> None:
    """`status`/`show --refresh` can mark a job "done" from lifecycle alone,
    without ever fetching a result. `collect` must not mistake that for
    already-collected and skip the fetch.
    """
    monkeypatch.setenv("HERDR_ENV", "1")
    job = jobs.new_job(task="t", directory="/r", kind="copilot")
    job["status"] = "done"
    jobs.save(job)

    monkeypatch.setattr(
        herdr, "agent_wait", lambda *a, **k: {"agent": {"agent_status": "done"}}
    )
    monkeypatch.setattr(herdr, "agent_read", lambda *a, **k: "the answer")

    args = argparse.Namespace(
        job_id=job["id"],
        wait=True,
        timeout=None,
        lines=400,
        refresh=False,
        raw=False,
        json=False,
    )
    rc = cmd_collect(args)

    assert rc == 0
    assert jobs.load(job["id"])["result"] == "the answer"


def test_collect_skips_refetch_once_result_is_stored(monkeypatch) -> None:
    monkeypatch.setenv("HERDR_ENV", "1")
    job = jobs.new_job(task="t", directory="/r", kind="copilot")
    job["status"] = "done"
    job["result"] = "already have this"
    jobs.save(job)

    def _boom(*a, **k) -> NoReturn:
        raise AssertionError("should not call herdr when result is already stored")

    monkeypatch.setattr(herdr, "agent_wait", _boom)
    monkeypatch.setattr(herdr, "agent_get", _boom)

    args = argparse.Namespace(
        job_id=job["id"],
        wait=True,
        timeout=None,
        lines=400,
        refresh=False,
        raw=False,
        json=False,
    )
    rc = cmd_collect(args)

    assert rc == 0
    assert jobs.load(job["id"])["result"] == "already have this"


def test_collect_prefers_session_file_over_pane_scrape(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HERDR_ENV", "1")
    session_file = tmp_path / "events.jsonl"
    session_file.write_text(
        json.dumps(
            {
                "type": "assistant.message",
                "data": {
                    "phase": "final_answer",
                    "content": "clean answer from session file",
                },
            }
        )
        + "\n"
    )
    job = jobs.new_job(task="t", directory="/r", kind="copilot")
    job["session_file"] = str(session_file)
    jobs.save(job)

    monkeypatch.setattr(
        herdr, "agent_wait", lambda *a, **k: {"agent": {"agent_status": "done"}}
    )

    def _boom(*a, **k) -> NoReturn:
        raise AssertionError(
            "should not scrape the pane when the session file resolves"
        )

    monkeypatch.setattr(herdr, "agent_read", _boom)

    args = argparse.Namespace(
        job_id=job["id"],
        wait=True,
        timeout=None,
        lines=400,
        refresh=False,
        raw=False,
        json=False,
    )
    rc = cmd_collect(args)

    assert rc == 0
    assert jobs.load(job["id"])["result"] == "clean answer from session file"


def _make_job(status: str, task: str = "t") -> dict:
    job = jobs.new_job(task=task, directory="/r", kind="copilot")
    job["status"] = status
    jobs.save(job)
    return job


def test_clear_defaults_to_done_jobs_only() -> None:
    done = _make_job("done")
    working = _make_job("working")

    rc = cmd_clear(argparse.Namespace(job_ids=[], status=None, all=False, json=False))

    assert rc == 0
    with pytest.raises(KeyError):
        jobs.load(done["id"])
    assert jobs.load(working["id"])["status"] == "working"


def test_clear_with_status_filters_to_those_statuses() -> None:
    error = _make_job("error")
    done = _make_job("done")

    rc = cmd_clear(
        argparse.Namespace(job_ids=[], status=["error"], all=False, json=False)
    )

    assert rc == 0
    with pytest.raises(KeyError):
        jobs.load(error["id"])
    assert jobs.load(done["id"])["status"] == "done"


def test_clear_all_ignores_status() -> None:
    done = _make_job("done")
    working = _make_job("working")

    rc = cmd_clear(argparse.Namespace(job_ids=[], status=None, all=True, json=False))

    assert rc == 0
    with pytest.raises(KeyError):
        jobs.load(done["id"])
    with pytest.raises(KeyError):
        jobs.load(working["id"])


def test_clear_specific_job_ids_ignores_status() -> None:
    working = _make_job("working")
    other_done = _make_job("done")

    rc = cmd_clear(
        argparse.Namespace(job_ids=[working["id"]], status=None, all=False, json=False)
    )

    assert rc == 0
    with pytest.raises(KeyError):
        jobs.load(working["id"])
    assert jobs.load(other_done["id"])["status"] == "done"


def test_clear_no_matching_jobs_is_a_noop(capsys) -> None:
    _make_job("working")

    rc = cmd_clear(argparse.Namespace(job_ids=[], status=None, all=False, json=False))

    assert rc == 0
    assert "no matching jobs" in capsys.readouterr().out
