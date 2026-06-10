"""Tests for scripts/bump_version.py prerelease bump semantics."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bump_version.py"
_spec = importlib.util.spec_from_file_location("bump_version", _SCRIPT)
assert _spec and _spec.loader
_bump = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bump)


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        ("0.2.0-beta.1", "0.2.0-beta.2"),
        ("0.2.0-beta.2", "0.2.0-beta.3"),
        ("0.2.0-alpha.1", "0.2.0-alpha.2"),
        ("0.2.0-rc.1", "0.2.0-rc.2"),
        ("0.2.0b1", "0.2.0b2"),
        ("0.2.0a1", "0.2.0a2"),
        ("0.2.0rc1", "0.2.0rc2"),
        ("0.1.0", "0.1.1a1"),
    ],
)
def test_bump_prerelease(current: str, expected: str) -> None:
    assert _bump.bump_prerelease(current) == expected


def test_bump_prerelease_rejects_unknown_suffix() -> None:
    with pytest.raises(ValueError, match="unrecognized suffix"):
        _bump.bump_prerelease("0.2.0-dev.1")


@pytest.mark.parametrize(
    "pyproject",
    [
        # Simple case: version is the only [project] key
        '[project]\nversion = "0.1.0"\n',
        # name above version (the current real-world shape)
        '[project]\nname = "x"\nversion = "0.1.0"\n',
        # Array-valued keys above version (the brittle case the new pattern fixes)
        '[project]\nclassifiers = ["A", "B"]\nversion = "0.1.0"\n',
        '[project]\ndependencies = []\nversion = "0.1.0"\n',
        '[project]\nkeywords = ["a"]\nversion = "0.1.0"\n',
        # Multiple bracket-containing keys above version
        (
            '[project]\nname = "x"\nclassifiers = ["A"]\n'
            'dependencies = ["dep"]\nversion = "0.1.0"\n'
        ),
        # Sibling [tool.X] table BEFORE [project] (must not shadow)
        '[tool.commitizen]\nversion = "TOOL"\n[project]\nversion = "0.1.0"\n',
        # Sibling [tool.X] table AFTER [project] (must not be touched)
        '[project]\nversion = "0.1.0"\n[tool.commitizen]\nversion = "TOOL"\n',
    ],
)
def test_root_project_version_re_replaces_project_version(pyproject: str) -> None:
    new_text, count = _bump.ROOT_PROJECT_VERSION_RE.subn(
        r'\1"REPLACED"', pyproject, count=1
    )
    assert count == 1, f"expected one match, got {count} in {pyproject!r}"
    assert 'version = "REPLACED"' in new_text
    # Make sure sibling [tool.X] versions stay untouched.
    if '"TOOL"' in pyproject:
        assert '"TOOL"' in new_text


@pytest.mark.parametrize(
    "pyproject",
    [
        # No [project] table at all
        '[tool.x]\nversion = "Y"\n',
        # [project] without a version key
        '[project]\nname = "x"\n[tool.y]\n',
        # version key inside a [project.subtable], not [project] itself
        '[project]\nname = "x"\n[project.urls]\nversion = "X"\n',
    ],
)
def test_root_project_version_re_rejects_missing_version(pyproject: str) -> None:
    _new_text, count = _bump.ROOT_PROJECT_VERSION_RE.subn(
        r'\1"REPLACED"', pyproject, count=1
    )
    assert count == 0, f"expected no match in {pyproject!r}"


def test_plugin_manifest_version_re_replaces_only_the_version() -> None:
    manifest = (
        "{\n"
        '  "name": "pipefy",\n'
        '  "version": "0.2.0-beta.1",\n'
        '  "homepage": "https://github.com/pipefy/ai-toolkit"\n'
        "}\n"
    )
    new_text, count = _bump.PLUGIN_MANIFEST_VERSION_RE.subn(
        r'\1"0.2.0-beta.2"', manifest, count=1
    )
    assert count == 1
    assert '"version": "0.2.0-beta.2"' in new_text
    # group(2) is the current version that verify mode reads back.
    assert _bump.PLUGIN_MANIFEST_VERSION_RE.search(manifest).group(2) == "0.2.0-beta.1"
