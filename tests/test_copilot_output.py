import json
from pathlib import Path

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
    result = copilot_output.extract_answer_from_pane(SAMPLE_PANE)

    assert "Today is Wednesday, September 2, 2026." in result
    assert "Copilot v1.0.82 uses AI" not in result
    assert "Current   Sessions   Issues" not in result
    assert "what day is it today" not in result
    assert "AIC used" not in result
    assert "~/r/cop" not in result
    assert "open sidebar" not in result


def test_extract_answer_keeps_tool_call_trace() -> None:
    result = copilot_output.extract_answer_from_pane(SAMPLE_PANE)

    assert "date -d '2026-09-02'" in result


def test_extract_answer_uses_last_turn_when_multiple_present() -> None:
    two_turns = SAMPLE_PANE + SAMPLE_PANE.replace(
        "Today is Wednesday, September 2, 2026.", "Second answer here."
    )

    result = copilot_output.extract_answer_from_pane(two_turns)

    assert "Second answer here." in result
    assert "Today is Wednesday" not in result


def test_extract_answer_falls_back_when_markers_missing() -> None:
    plain = "just some text with no TUI chrome at all"
    assert copilot_output.extract_answer_from_pane(plain) == plain


def test_session_events_path_keyed_by_session_id() -> None:
    path = copilot_output.session_events_path("abc-123")
    assert path.name == "events.jsonl"
    assert path.parent.name == "abc-123"
    assert path.parent.parent.name == "session-state"


def _events_file(tmp_path, events) -> Path:
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return path


def _final_answer_event(content: str, turn: str = "0") -> dict:
    return {
        "type": "assistant.message",
        "data": {"phase": "final_answer", "content": content, "turnId": turn},
    }


def test_extract_final_answer_reads_content(tmp_path) -> None:
    path = _events_file(
        tmp_path,
        [
            {"type": "session.start", "data": {}},
            _final_answer_event("the clean answer"),
            {"type": "assistant.turn_end", "data": {"turnId": "0"}},
        ],
    )
    assert copilot_output.extract_final_answer(path) == "the clean answer"


def test_extract_final_answer_uses_last_one(tmp_path) -> None:
    path = _events_file(
        tmp_path,
        [
            _final_answer_event("first turn's answer", turn="0"),
            _final_answer_event("second turn's answer", turn="1"),
        ],
    )
    assert copilot_output.extract_final_answer(path) == "second turn's answer"


def test_extract_final_answer_none_when_no_final_answer_yet(tmp_path) -> None:
    path = _events_file(
        tmp_path,
        [
            {"type": "session.start", "data": {}},
            {"type": "model.model_call_started", "data": {}},
        ],
    )
    assert copilot_output.extract_final_answer(path) is None


def test_extract_final_answer_none_when_file_missing(tmp_path) -> None:
    assert (
        copilot_output.extract_final_answer(tmp_path / "does-not-exist.jsonl") is None
    )


def test_extract_final_answer_skips_bad_lines(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("not json\n" + json.dumps(_final_answer_event("ok answer")) + "\n")
    assert copilot_output.extract_final_answer(path) == "ok answer"
