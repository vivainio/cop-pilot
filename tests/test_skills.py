"""Tests for cop install-skills command."""

import argparse
from pathlib import Path
from types import ModuleType

import pytest


def test_install_skills_copies_skill_md(tmp_path) -> None:
    from cop.skills import install_skills_command

    args = argparse.Namespace(skills_dir=str(tmp_path))
    install_skills_command(args)

    dest = tmp_path / "cop"
    assert (dest / "SKILL.md").exists()


def test_install_skills_creates_target_dir(tmp_path) -> None:
    from cop.skills import install_skills_command

    target = tmp_path / "nested" / "skills"
    args = argparse.Namespace(skills_dir=str(target))
    install_skills_command(args)

    assert (target / "cop" / "SKILL.md").exists()


def test_install_skills_skill_md_has_name(tmp_path) -> None:
    from cop.skills import install_skills_command

    args = argparse.Namespace(skills_dir=str(tmp_path))
    install_skills_command(args)

    content = (tmp_path / "cop" / "SKILL.md").read_text()
    assert "name: cop" in content


class TestFrontmatterUpdated:
    def test_extracts_updated_field(self) -> None:
        from cop.skills import _frontmatter_updated

        text = "---\nupdated: 2026-07-16\n---\n\nbody"
        assert _frontmatter_updated(text) == "2026-07-16"

    def test_returns_none_without_frontmatter(self) -> None:
        from cop.skills import _frontmatter_updated

        assert _frontmatter_updated("no frontmatter here") is None

    def test_returns_none_without_closing_delimiter(self) -> None:
        from cop.skills import _frontmatter_updated

        assert _frontmatter_updated("---\nupdated: 2026-07-16\nno closing") is None

    def test_returns_none_when_field_missing(self) -> None:
        from cop.skills import _frontmatter_updated

        text = "---\nname: cop\n---\n\nbody"
        assert _frontmatter_updated(text) is None


class TestCheckSkillStaleness:
    def _setup(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        bundled_updated: str | None,
        installed_updated: str | None,
        installed_exists: bool = True,
    ) -> ModuleType:
        from cop import skills

        bundled_root = tmp_path / "bundled"
        (bundled_root / "skills" / "cop").mkdir(parents=True)
        bundled_front_matter = (
            f"updated: {bundled_updated}\n" if bundled_updated else ""
        )
        (bundled_root / "skills" / "cop" / "SKILL.md").write_text(
            f"---\n{bundled_front_matter}---\n\nBundled body"
        )
        monkeypatch.setattr(skills, "files", lambda package: bundled_root)

        if installed_exists:
            installed_md = tmp_path / "installed" / "SKILL.md"
            installed_md.parent.mkdir(parents=True)
            installed_front_matter = (
                f"updated: {installed_updated}\n" if installed_updated else ""
            )
            installed_md.write_text(
                f"---\n{installed_front_matter}---\n\nInstalled body"
            )
        else:
            installed_md = tmp_path / "installed" / "SKILL.md"  # never created
        monkeypatch.setattr(skills, "INSTALLED_SKILL_MD", installed_md)

        marker = tmp_path / "skill-check.txt"
        monkeypatch.setattr(skills, "STALE_CHECK_MARKER", marker)

        return skills

    def test_prints_nudge_when_installed_is_older(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        skills = self._setup(
            tmp_path,
            monkeypatch,
            bundled_updated="2026-07-16",
            installed_updated="2026-07-03",
        )

        skills.check_skill_staleness()

        captured = capsys.readouterr()
        assert "note: installed cop skill is outdated" in captured.err
        assert "installed: 2026-07-03" in captured.err
        assert "latest: 2026-07-16" in captured.err
        assert "cop install-skills" in captured.err

    def test_silent_when_up_to_date(self, tmp_path, monkeypatch, capsys) -> None:
        skills = self._setup(
            tmp_path,
            monkeypatch,
            bundled_updated="2026-07-16",
            installed_updated="2026-07-16",
        )

        skills.check_skill_staleness()

        assert capsys.readouterr().err == ""

    def test_silent_when_installed_is_newer(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        skills = self._setup(
            tmp_path,
            monkeypatch,
            bundled_updated="2026-07-01",
            installed_updated="2026-07-16",
        )

        skills.check_skill_staleness()

        assert capsys.readouterr().err == ""

    def test_silent_when_no_installed_skill(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        skills = self._setup(
            tmp_path,
            monkeypatch,
            bundled_updated="2026-07-16",
            installed_updated=None,
            installed_exists=False,
        )

        skills.check_skill_staleness()

        assert capsys.readouterr().err == ""

    def test_silent_when_bundled_has_no_updated_field(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        skills = self._setup(
            tmp_path, monkeypatch, bundled_updated=None, installed_updated="2026-07-03"
        )

        skills.check_skill_staleness()

        assert capsys.readouterr().err == ""

    def test_nudges_with_unknown_when_installed_has_no_updated_field(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        skills = self._setup(
            tmp_path, monkeypatch, bundled_updated="2026-07-16", installed_updated=None
        )

        skills.check_skill_staleness()

        assert "installed: unknown" in capsys.readouterr().err

    def test_throttled_to_once_per_day(self, tmp_path, monkeypatch, capsys) -> None:
        skills = self._setup(
            tmp_path,
            monkeypatch,
            bundled_updated="2026-07-16",
            installed_updated="2026-07-03",
        )

        skills.check_skill_staleness()
        first = capsys.readouterr()
        assert "note: installed cop skill is outdated" in first.err

        skills.check_skill_staleness()
        second = capsys.readouterr()
        assert second.err == ""

    def test_writes_marker_with_todays_date(self, tmp_path, monkeypatch) -> None:
        from datetime import datetime, timezone

        skills = self._setup(
            tmp_path,
            monkeypatch,
            bundled_updated="2026-07-16",
            installed_updated="2026-07-16",
        )

        skills.check_skill_staleness()

        today = datetime.now(tz=timezone.utc).date().isoformat()
        assert skills.STALE_CHECK_MARKER.read_text().strip() == today
