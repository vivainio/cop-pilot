from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def cop_home(tmp_path, monkeypatch) -> Path:
    """Point the job store at a throwaway directory for every test."""
    monkeypatch.setenv("COP_HOME", str(tmp_path))
    return tmp_path
