"""Flat-file job store for delegated tasks. One JSON file per job."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _default_base() -> Path:
    cache_home = os.environ.get("XDG_CACHE_HOME")
    return (Path(cache_home) if cache_home else Path.home() / ".cache") / "cop-pilot"


def _migrate_legacy_jobs(jobs_dir: Path) -> None:
    """One-time move from the old ~/.cop/jobs location to the new XDG cache
    dir, so pre-existing job history isn't silently orphaned."""
    legacy = Path.home() / ".cop" / "jobs"
    if jobs_dir.exists() or not legacy.exists():
        return
    jobs_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(legacy), str(jobs_dir))


def base_dir() -> Path:
    base = os.environ.get("COP_HOME")
    return Path(base) if base else _default_base()


def store_dir() -> Path:
    base = os.environ.get("COP_HOME")
    jobs = base_dir() / "jobs"
    if base is None:
        _migrate_legacy_jobs(jobs)
    jobs.mkdir(parents=True, exist_ok=True)
    return jobs


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _path(job_id: str) -> Path:
    return store_dir() / f"{job_id}.json"


def new_job(*, task: str, directory: str, kind: str) -> dict:
    job_id = uuid.uuid4().hex[:8]
    while _path(job_id).exists():
        job_id = uuid.uuid4().hex[:8]
    job = {
        "id": job_id,
        "name": f"cop-{job_id}",
        "pane_id": None,
        "kind": kind,
        "dir": directory,
        "task": task,
        "status": "pending",
        "result": None,
        "error": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    save(job)
    return job


def save(job: dict) -> None:
    job["updated_at"] = _now()
    path = _path(job["id"])
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(job, indent=2) + "\n")
    tmp.replace(path)


def list_jobs() -> list[dict]:
    jobs = []
    for path in store_dir().glob("*.json"):
        try:
            jobs.append(json.loads(path.read_text()))
        except json.JSONDecodeError:
            continue
    jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
    return jobs


def resolve_id(job_id_prefix: str) -> str:
    exact = _path(job_id_prefix)
    if exact.exists():
        return job_id_prefix
    matches = [p.stem for p in store_dir().glob(f"{job_id_prefix}*.json")]
    if not matches:
        raise KeyError(f"no job matches id '{job_id_prefix}'")
    if len(matches) > 1:
        raise KeyError(
            f"ambiguous job id '{job_id_prefix}': matches {', '.join(sorted(matches))}"
        )
    return matches[0]


def load(job_id_prefix: str) -> dict:
    job_id = resolve_id(job_id_prefix)
    return json.loads(_path(job_id).read_text())


def remove(job_id_prefix: str) -> str:
    """Delete a job's file. Returns the resolved job id. Does not touch
    any herdr pane/tab/worktree the job may have created."""
    job_id = resolve_id(job_id_prefix)
    _path(job_id).unlink()
    return job_id
