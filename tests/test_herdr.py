from cop.herdr import HerdrError


def test_herdr_error_parses_json_stderr() -> None:
    err = HerdrError(
        ["agent", "get", "x"],
        1,
        '{"error": {"code": "not_found", "message": "no such agent"}}',
    )

    assert "agent get x" in str(err)
    assert "not_found" in str(err)
    assert "no such agent" in str(err)


def test_herdr_error_falls_back_to_raw_stderr() -> None:
    err = HerdrError(["pane", "read", "x"], 1, "not json at all")

    assert "not json at all" in str(err)
