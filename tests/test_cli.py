from cop.cli import _agent_name, _agent_status


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


def test_agent_status_reads_nested_agent_field() -> None:
    state = {"agent": {"agent_status": "idle"}, "type": "agent_info"}
    assert _agent_status(state) == "idle"


def test_agent_status_defaults_to_unknown() -> None:
    assert _agent_status({}) == "unknown"
