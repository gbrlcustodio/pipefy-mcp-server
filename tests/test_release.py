"""Tests for scripts/release.py pure logic (CHANGELOG stamping, version parsing)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release.py"
_spec = importlib.util.spec_from_file_location("release", _SCRIPT)
assert _spec and _spec.loader
_release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_release)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0.2.0-beta.1", "0.2.0b1"),
        ("0.2.0-alpha.3", "0.2.0a3"),
        ("1.0.0rc2", "1.0.0rc2"),
        ("1.2.3", "1.2.3"),
    ],
)
def test_pep440_normalizes(raw: str, expected: str) -> None:
    assert _release.pep440(raw) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("pipefy, version 0.2.0b1", {"0.2.0b1"}),
        ("pipefy-cli 1.2.3", {"1.2.3"}),
        ("no version here", set()),
        ("0.2.0-beta.1 build", {"0.2.0b1"}),
    ],
)
def test_pep440_candidates(text: str, expected: set[str]) -> None:
    assert _release.pep440_candidates(text) == expected


def test_unreleased_re_captures_heading_and_body() -> None:
    text = (
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "### Added\n- a thing\n\n"
        "## [1.0.0] - 2026-01-01\n\n- old\n"
    )
    m = _release.UNRELEASED_RE.search(text)
    assert m is not None
    assert m.group(1).startswith("## [Unreleased]")
    assert "a thing" in m.group(2)
    assert "old" not in m.group(2)


def test_stamp_changelog_renames_and_reseeds(tmp_path: Path, monkeypatch) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "### Added\n- new feature\n\n"
        "## [1.0.0] - 2026-01-01\n\n- old\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(_release, "CHANGELOG", changelog)

    _release.stamp_changelog("2.0.0")
    out = changelog.read_text(encoding="utf-8")

    # A fresh empty Unreleased is re-seeded above the dated version section.
    assert "## [Unreleased]\n\n## [2.0.0] - " in out
    # The accumulated notes moved under the new version, not lost.
    idx_version = out.index("## [2.0.0]")
    assert "new feature" in out[idx_version:]
    # The prior release section is untouched.
    assert "## [1.0.0] - 2026-01-01" in out


def test_compute_target_version(monkeypatch) -> None:
    monkeypatch.setattr(
        _release.bump_version, "read_sdk_version", lambda: "0.3.0-beta.1"
    )
    assert _release.compute_target_version("major") == ("0.3.0-beta.1", "1.0.0")
    assert _release.compute_target_version("minor") == ("0.3.0-beta.1", "0.4.0")
    assert _release.compute_target_version("patch") == ("0.3.0-beta.1", "0.3.1")
    # prerelease increments the current track; it does not promote alpha->beta.
    assert _release.compute_target_version("prerelease") == (
        "0.3.0-beta.1",
        "0.3.0-beta.2",
    )
    # version= is the escape hatch for a cross-track or arbitrary jump.
    assert _release.compute_target_version("version=0.3.0-rc.1") == (
        "0.3.0-beta.1",
        "0.3.0-rc.1",
    )


def test_newest_run_id_skips_excluded(monkeypatch) -> None:
    # gh lists newest first; the snapshot of prior runs must be skipped so a
    # re-cut of the same tag waits for its genuinely new run.
    monkeypatch.setattr(_release, "_release_run_ids", lambda tag: ["300", "200", "100"])
    assert _release._newest_run_id("v1", frozenset()) == "300"
    assert _release._newest_run_id("v1", frozenset({"300"})) == "200"
    assert _release._newest_run_id("v1", frozenset({"300", "200", "100"})) == ""


def test_compute_target_version_rejects_unknown(monkeypatch) -> None:
    monkeypatch.setattr(_release.bump_version, "read_sdk_version", lambda: "0.3.0")
    with pytest.raises(_release.ReleaseError):
        _release.compute_target_version("bogus")


def test_stamp_changelog_requires_unreleased(tmp_path: Path, monkeypatch) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [1.0.0] - 2026-01-01\n", encoding="utf-8")
    monkeypatch.setattr(_release, "CHANGELOG", changelog)

    with pytest.raises(_release.ReleaseError):
        _release.stamp_changelog("2.0.0")
