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


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        # Bare dependency gains a pin.
        ('"pipefy-sdk"', '"pipefy-sdk==9.9.9"'),
        # Already-pinned dependency is re-pinned to the new version.
        ('"pipefy-sdk==0.2.0-beta.3"', '"pipefy-sdk==9.9.9"'),
        # Single quotes are handled too.
        ("'pipefy-sdk'", "'pipefy-sdk==9.9.9'"),
    ],
)
def test_workspace_dep_pin_re_rewrites_dependency(entry: str, expected: str) -> None:
    new_text, count = _bump.workspace_dep_pin_re("pipefy-sdk").subn(
        r"\g<1>pipefy-sdk==9.9.9\g<2>", entry, count=1
    )
    assert count == 1
    assert new_text == expected


@pytest.mark.parametrize(
    "text",
    [
        # An unquoted [tool.uv.sources] key must not be pinned (no quotes).
        "pipefy-sdk = { workspace = true }",
        # A parenthesized mention inside a description must not be pinned
        # (the name is not the whole quoted string).
        'description = "Typer CLI for Pipefy (pipefy-sdk)."',
    ],
)
def test_workspace_dep_pin_re_leaves_non_dependencies_untouched(text: str) -> None:
    _new_text, count = _bump.workspace_dep_pin_re("pipefy-sdk").subn(
        r"\g<1>pipefy-sdk==9.9.9\g<2>", text, count=1
    )
    assert count == 0, f"unexpectedly matched in {text!r}"


def test_workspace_dep_pins_never_target_own_name() -> None:
    """The own-name collision (name = "x" is a full quoted string) is avoided by
    the pin map never listing a package's own distribution name."""
    own_name = {
        "sdk": "pipefy-sdk",
        "mcp": "pipefy-mcp-server",
        "cli": "pipefy-cli",
        "auth": "pipefy-auth",
        "infra": "pipefy-infra",
    }
    for path, deps in _bump.WORKSPACE_DEP_PINS.items():
        pkg_dir = path.parent.name
        assert own_name[pkg_dir] not in deps, (
            f"{path} would pin its own name {own_name[pkg_dir]!r}"
        )
