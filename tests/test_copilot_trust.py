from pathlib import Path

from cop import copilot_trust

SAMPLE_CONFIG = """// User settings belong in settings.json.
// This file is managed automatically.
{
  "trustedFolders": [
    "/home/v/one",
    "/home/v/two"
  ],
  "copilotTokens": {
    "https://github.com:me": "gho_super-secret-token"
  }
}
"""


def _write(tmp_path, monkeypatch, content=SAMPLE_CONFIG) -> Path:
    config_path = tmp_path / "config.json"
    config_path.write_text(content)
    monkeypatch.setattr(copilot_trust, "CONFIG_PATH", config_path)
    return config_path


def test_is_trusted_true_for_listed_folder(tmp_path, monkeypatch) -> None:
    _write(tmp_path, monkeypatch)
    assert copilot_trust.is_trusted("/home/v/one") is True


def test_is_trusted_false_for_unlisted_folder(tmp_path, monkeypatch) -> None:
    _write(tmp_path, monkeypatch)
    assert copilot_trust.is_trusted("/home/v/three") is False


def test_is_trusted_false_when_config_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(copilot_trust, "CONFIG_PATH", tmp_path / "does-not-exist.json")
    assert copilot_trust.is_trusted("/home/v/one") is False


def test_trust_adds_folder_and_reports_change(tmp_path, monkeypatch) -> None:
    config_path = _write(tmp_path, monkeypatch)

    changed = copilot_trust.trust("/home/v/three")

    assert changed is True
    assert copilot_trust.is_trusted("/home/v/three") is True
    # unrelated content -- notably the token -- is left untouched
    assert "gho_super-secret-token" in config_path.read_text()


def test_trust_is_a_noop_when_already_trusted(tmp_path, monkeypatch) -> None:
    _write(tmp_path, monkeypatch)

    changed = copilot_trust.trust("/home/v/one")

    assert changed is False


def test_trust_on_empty_trusted_folders_list(tmp_path, monkeypatch) -> None:
    empty = SAMPLE_CONFIG.replace(
        '"trustedFolders": [\n    "/home/v/one",\n    "/home/v/two"\n  ],',
        '"trustedFolders": [],',
    )
    _write(tmp_path, monkeypatch, empty)

    assert copilot_trust.trust("/home/v/three") is True
    assert copilot_trust.is_trusted("/home/v/three") is True
