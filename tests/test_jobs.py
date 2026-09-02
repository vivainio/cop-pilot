import pytest

from cop import jobs


def test_new_job_has_expected_fields() -> None:
    job = jobs.new_job(task="do the thing", directory="/tmp/repo", kind="copilot")

    assert job["task"] == "do the thing"
    assert job["dir"] == "/tmp/repo"
    assert job["kind"] == "copilot"
    assert job["status"] == "pending"
    assert job["result"] is None
    assert job["name"] == f"cop-{job['id']}"


def test_new_job_ids_are_unique() -> None:
    ids = {
        jobs.new_job(task="t", directory="/r", kind="copilot")["id"] for _ in range(20)
    }
    assert len(ids) == 20


def test_save_round_trips_and_updates_timestamp() -> None:
    job = jobs.new_job(task="t", directory="/r", kind="copilot")
    first_updated = job["updated_at"]

    job["status"] = "done"
    job["result"] = "the answer"
    jobs.save(job)

    reloaded = jobs.load(job["id"])
    assert reloaded["status"] == "done"
    assert reloaded["result"] == "the answer"
    assert reloaded["updated_at"] >= first_updated


def test_list_jobs_sorted_newest_first() -> None:
    older = jobs.new_job(task="older", directory="/r", kind="copilot")
    older["created_at"] = "2020-01-01T00:00:00+00:00"
    jobs.save(older)
    newer = jobs.new_job(task="newer", directory="/r", kind="copilot")
    newer["created_at"] = "2030-01-01T00:00:00+00:00"
    jobs.save(newer)

    listed = jobs.list_jobs()
    assert [j["id"] for j in listed] == [newer["id"], older["id"]]


def test_resolve_id_by_prefix() -> None:
    job = jobs.new_job(task="t", directory="/r", kind="copilot")
    prefix = job["id"][:4]

    assert jobs.resolve_id(prefix) == job["id"]


def test_resolve_id_unknown_raises() -> None:
    with pytest.raises(KeyError, match="no job matches"):
        jobs.resolve_id("nonexistent")


def test_resolve_id_ambiguous_raises() -> None:
    # Force a collision by writing two jobs that share a prefix.
    a = jobs.new_job(task="a", directory="/r", kind="copilot")
    a["id"] = "abc111"
    jobs.save(a)
    b = jobs.new_job(task="b", directory="/r", kind="copilot")
    b["id"] = "abc222"
    jobs.save(b)

    with pytest.raises(KeyError, match="ambiguous"):
        jobs.resolve_id("abc")
