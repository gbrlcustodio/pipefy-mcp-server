"""Tests for `pipefy skills list` and `pipefy skills show`."""

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from pipefy_cli.main import app


@pytest.fixture
def runner():
    return CliRunner(mix_stderr=False)


FAKE_SKILL_CONTENT = textwrap.dedent("""\
    ---
    name: pipefy-fake-skill
    description: A fake skill for testing.
    tags: [test]
    ---

    # Fake Skill

    Body content here.
""")

FAKE_SKILL_B = textwrap.dedent("""\
    ---
    name: pipefy-second-skill
    description: Second skill for testing.
    ---

    # Second Skill
""")

FAKE_SKILL_FOLDED = textwrap.dedent("""\
    ---
    name: pipefy-folded-skill
    description: >
      Use this skill when testing folded YAML scalars in the CLI parser.
    tags: [test]
    ---

    # Folded

    Body.
""")


def _make_skill_files(tmp_path: Path) -> Path:
    """Write two fake skill .md files to a temp directory."""
    (tmp_path / "pipefy-fake-skill.md").write_text(FAKE_SKILL_CONTENT, encoding="utf-8")
    (tmp_path / "pipefy-second-skill.md").write_text(FAKE_SKILL_B, encoding="utf-8")
    return tmp_path


def test_skills_list_returns_skill_names(runner, tmp_path):
    skills_dir = _make_skill_files(tmp_path)
    with patch(
        "pipefy_cli.commands.skills._bundled_skills_dir", return_value=skills_dir
    ):
        result = runner.invoke(app, ["skills", "list"])
    assert result.exit_code == 0, result.output
    assert "pipefy-fake-skill" in result.output
    assert "pipefy-second-skill" in result.output


def test_skills_list_shows_description(runner, tmp_path):
    skills_dir = _make_skill_files(tmp_path)
    with patch(
        "pipefy_cli.commands.skills._bundled_skills_dir", return_value=skills_dir
    ):
        result = runner.invoke(app, ["skills", "list"])
    assert "A fake skill for testing" in result.output


def test_skills_list_folded_description(runner, tmp_path):
    """Folded YAML description must not collapse to empty (regression for bundled skills)."""
    (tmp_path / "pipefy-folded-skill.md").write_text(
        FAKE_SKILL_FOLDED, encoding="utf-8"
    )
    with patch("pipefy_cli.commands.skills._bundled_skills_dir", return_value=tmp_path):
        result = runner.invoke(app, ["skills", "list"])
    assert result.exit_code == 0, result.output
    assert "Use this skill when testing folded YAML" in result.output


def test_skills_list_nonempty_when_bundled(runner):
    """Bundled starter pack must expose multiple skills with descriptions."""
    result = runner.invoke(app, ["skills", "list"])
    assert result.exit_code == 0, result.output
    lines = [ln for ln in result.output.splitlines() if ln.startswith("pipefy-")]
    assert len(lines) >= 5, result.output
    assert "Use this skill" in result.output


def test_skills_list_invalid_frontmatter_exits_2(runner, tmp_path):
    (tmp_path / "broken.md").write_text(
        "---\nname: x\ndescription: y\n[\n---\n",
        encoding="utf-8",
    )
    with patch("pipefy_cli.commands.skills._bundled_skills_dir", return_value=tmp_path):
        result = runner.invoke(app, ["skills", "list"])
    assert result.exit_code == 2
    assert "invalid YAML frontmatter" in result.stderr


def test_skills_list_empty_bundle_exits_2(runner, tmp_path):
    with patch("pipefy_cli.commands.skills._bundled_skills_dir", return_value=tmp_path):
        result = runner.invoke(app, ["skills", "list"])
    assert result.exit_code == 2


def test_skills_show_prints_body(runner, tmp_path):
    skills_dir = _make_skill_files(tmp_path)
    with patch(
        "pipefy_cli.commands.skills._bundled_skills_dir", return_value=skills_dir
    ):
        result = runner.invoke(app, ["skills", "show", "pipefy-fake-skill"])
    assert result.exit_code == 0, result.output
    assert "Body content here" in result.output


def test_skills_show_unprefixed_slug(runner, tmp_path):
    skills_dir = _make_skill_files(tmp_path)
    with patch(
        "pipefy_cli.commands.skills._bundled_skills_dir", return_value=skills_dir
    ):
        result = runner.invoke(app, ["skills", "show", "fake-skill"])
    assert result.exit_code == 0, result.output
    assert "Body content here" in result.output


def test_skills_show_missing_name_exits_2(runner, tmp_path):
    skills_dir = _make_skill_files(tmp_path)
    with patch(
        "pipefy_cli.commands.skills._bundled_skills_dir", return_value=skills_dir
    ):
        result = runner.invoke(app, ["skills", "show", "does-not-exist"])
    assert result.exit_code == 2


def test_skills_show_real_bundled_skill(runner):
    """Bundled starter pack must be readable by full name or short slug."""
    for arg in ("pipefy-pipes-and-cards", "pipes-and-cards"):
        result = runner.invoke(app, ["skills", "show", arg])
        assert result.exit_code == 0, result.output
        assert "name: pipefy-pipes-and-cards" in result.output
