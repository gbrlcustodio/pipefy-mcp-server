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
    ("dep", "text"),
    [
        # Unpinned dependency
        ("pipefy", '    "pipefy",\n'),
        # Already pinned (re-pin to a new version)
        ("pipefy", '    "pipefy==0.1.0",\n'),
        ("pipefy-auth", '    "pipefy-auth==0.2.0-beta.3",\n'),
    ],
)
def test_workspace_dep_pin_re_matches_and_repins(dep: str, text: str) -> None:
    new_text, count = _bump.workspace_dep_pin_re(dep).subn(
        rf"\g<1>{dep}==9.9.9\g<1>", text, count=1
    )
    assert count == 1
    assert f'"{dep}==9.9.9"' in new_text


@pytest.mark.parametrize(
    "text",
    [
        # `pipefy` must not match the longer sibling name
        '    "pipefy-infra",\n',
        '    "pipefy-infra==0.1.0",\n',
        # Unquoted [tool.uv.sources] key
        "pipefy = { workspace = true }\n",
        # A package's own name field is `pipefy-cli`, not a bare `pipefy`
        'name = "pipefy-cli"\n',
        # Bare mention inside a quoted description
        'description = "Typer CLI for Pipefy (pipefy)."\n',
    ],
)
def test_workspace_dep_pin_re_pipefy_does_not_overmatch(text: str) -> None:
    _new_text, count = _bump.workspace_dep_pin_re("pipefy").subn(
        r"\g<1>pipefy==9.9.9\g<1>", text, count=1
    )
    assert count == 0, f"expected no match in {text!r}"


@pytest.mark.parametrize(
    ("text", "expected_version"),
    [
        ('    "pipefy==0.3.0-alpha.1",\n', "0.3.0-alpha.1"),
        ('    "pipefy==1.2.3",\n', "1.2.3"),
        # Unpinned: matches, but group 2 is None (verify treats this as missing)
        ('    "pipefy",\n', None),
    ],
)
def test_workspace_dep_pin_re_captures_pin(
    text: str, expected_version: str | None
) -> None:
    m = _bump.workspace_dep_pin_re("pipefy").search(text)
    assert m is not None
    assert m.group(2) == expected_version


@pytest.mark.parametrize(
    "manifest",
    [
        '{\n  "name": "pipefy",\n  "version": "0.2.0-beta.1"\n}\n',
        # version before name, and with extra whitespace around the colon
        '{\n  "version" :  "0.2.0-beta.1",\n  "name": "pipefy"\n}\n',
    ],
)
def test_plugin_manifest_version_re_replaces_version(manifest: str) -> None:
    new_text, count = _bump.PLUGIN_MANIFEST_VERSION_RE.subn(
        r"\g<prefix>9.9.9\g<suffix>", manifest, count=1
    )
    assert count == 1
    assert '"version"' in new_text and "9.9.9" in new_text
    # The name key must not be rewritten.
    assert '"pipefy"' in new_text


def test_plugin_manifest_version_matches_real_manifest() -> None:
    text = _bump.PLUGIN_MANIFEST.read_text(encoding="utf-8")
    m = _bump.PLUGIN_MANIFEST_VERSION_RE.search(text)
    assert m is not None
    assert m.group("value") == _bump.read_sdk_version()


def test_workspace_dep_pins_never_list_own_name() -> None:
    # The re matches a package's own `name = "..."`, so a self-listing would
    # rewrite the name field. Guard the invariant the docstring relies on.
    own_names = {
        "packages/sdk/pyproject.toml": "pipefy",
        "packages/auth/pyproject.toml": "pipefy-auth",
        "packages/cli/pyproject.toml": "pipefy-cli",
        "packages/mcp/pyproject.toml": "pipefy-mcp-server",
    }
    for path, deps in _bump.WORKSPACE_DEP_PINS.items():
        rel = str(path.relative_to(_bump.REPO_ROOT))
        assert own_names[rel] not in deps


def test_package_pyprojects_derived_from_workspace() -> None:
    # Derived from [tool.uv.workspace].members, not a second hand-maintained
    # list, so a new member cannot skip the pin-map reconciliation.
    assert _bump.PACKAGE_PYPROJECTS
    for path in _bump.PACKAGE_PYPROJECTS:
        assert path.exists()


def test_verify_pin_map_consistent_with_repo() -> None:
    # Guards the invariant in CI: WORKSPACE_DEP_PINS lists exactly the
    # workspace siblings each package actually depends on.
    assert _bump.verify_pin_map() == []


def test_declared_sibling_deps_keeps_only_workspace_members(tmp_path: Path) -> None:
    members = {"pipefy", "pipefy-auth", "pipefy-infra"}
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project]\n"
        'name = "pipefy-cli"\n'
        'version = "0.1.0"\n'
        "dependencies = [\n"
        '    "pipefy==0.3.0-alpha.1",\n'
        '    "pipefy-auth==0.3.0-alpha.1",\n'
        '    "typer>=0.12",\n'
        "]\n",
        encoding="utf-8",
    )
    assert _bump.declared_sibling_deps(pyproject, members) == {"pipefy", "pipefy-auth"}


def _write_pkg(path: Path, name: str, deps: tuple[str, ...]) -> None:
    dep_lines = "".join(f'    "{d}",\n' for d in deps)
    path.write_text(
        f'[project]\nname = "{name}"\nversion = "0.1.0"\n'
        f"dependencies = [\n{dep_lines}]\n",
        encoding="utf-8",
    )


def test_verify_pin_map_flags_unpinned_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sdk = tmp_path / "sdk.toml"
    infra = tmp_path / "infra.toml"
    # sdk depends on pipefy-infra, but the pin map has no entry for it.
    _write_pkg(sdk, "pipefy", ("pipefy-infra==0.1.0",))
    _write_pkg(infra, "pipefy-infra", ())
    monkeypatch.setattr(_bump, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(_bump, "PACKAGE_PYPROJECTS", (sdk, infra))
    monkeypatch.setattr(_bump, "WORKSPACE_DEP_PINS", {})

    errors = _bump.verify_pin_map()

    assert any("missing from WORKSPACE_DEP_PINS" in e for e in errors)


def test_verify_pin_map_flags_stale_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sdk = tmp_path / "sdk.toml"
    infra = tmp_path / "infra.toml"
    # The map pins pipefy-infra for sdk, but sdk no longer declares it.
    _write_pkg(sdk, "pipefy", ())
    _write_pkg(infra, "pipefy-infra", ())
    monkeypatch.setattr(_bump, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(_bump, "PACKAGE_PYPROJECTS", (sdk, infra))
    monkeypatch.setattr(_bump, "WORKSPACE_DEP_PINS", {sdk: ("pipefy-infra",)})

    errors = _bump.verify_pin_map()

    assert any("no longer declares" in e for e in errors)


def test_verify_pin_map_flags_unknown_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sdk = tmp_path / "sdk.toml"
    stray = tmp_path / "stray.toml"
    _write_pkg(sdk, "pipefy", ())
    monkeypatch.setattr(_bump, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(_bump, "PACKAGE_PYPROJECTS", (sdk,))
    monkeypatch.setattr(_bump, "WORKSPACE_DEP_PINS", {stray: ("pipefy",)})

    errors = _bump.verify_pin_map()

    assert any("is not a workspace package" in e for e in errors)
