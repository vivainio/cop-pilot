from cop import copilot_output

SAMPLE_PANE = """  Current   Sessions   Issues   Pull requests   Gists

  ╭─╮╭─╮
  ╰─╯╰─╯  Copilot v1.0.82 uses AI.
  █ ▘▝ █  Check for mistakes.
   ▔▔▔▔

 ● Tip: /feedback
   └ Provide feedback about the CLI
 ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
  ❯ what day is it today                                          22:34
 ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
 $ Shell Calculate weekday for the provided date 2 lines…
   date -d '2026-09-02' '+%A, %B %-d, %Y'

 ● Today is Wednesday, September 2, 2026.




 ~/r/cop [⎇ main]                                    Session: 0.58 AIC used
╯▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
┃
╹▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
 ← open sidebar · / commands · ? help · tab next tab          GPT-5.6 Luna
"""


def test_extract_answer_strips_chrome() -> None:
    result = copilot_output.extract_answer(SAMPLE_PANE)

    assert "Today is Wednesday, September 2, 2026." in result
    assert "Copilot v1.0.82 uses AI" not in result
    assert "Current   Sessions   Issues" not in result
    assert "what day is it today" not in result
    assert "AIC used" not in result
    assert "~/r/cop" not in result
    assert "open sidebar" not in result


def test_extract_answer_keeps_tool_call_trace() -> None:
    result = copilot_output.extract_answer(SAMPLE_PANE)

    assert "date -d '2026-09-02'" in result


def test_extract_answer_uses_last_turn_when_multiple_present() -> None:
    two_turns = SAMPLE_PANE + SAMPLE_PANE.replace(
        "Today is Wednesday, September 2, 2026.", "Second answer here."
    )

    result = copilot_output.extract_answer(two_turns)

    assert "Second answer here." in result
    assert "Today is Wednesday" not in result


def test_extract_answer_falls_back_when_markers_missing() -> None:
    plain = "just some text with no TUI chrome at all"
    assert copilot_output.extract_answer(plain) == plain


def test_session_events_path_keyed_by_session_id() -> None:
    path = copilot_output.session_events_path("abc-123")
    assert path.name == "events.jsonl"
    assert path.parent.name == "abc-123"
    assert path.parent.parent.name == "session-state"
