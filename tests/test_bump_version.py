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


def _write_pkg(path: Path, name: str, deps: tuple[str, ...]) -> None:
    dep_lines = "".join(f'    "{d}",\n' for d in deps)
    path.write_text(
        f'[project]\nname = "{name}"\nversion = "0.1.0"\n'
        f"dependencies = [\n{dep_lines}]\n",
        encoding="utf-8",
    )


def test_package_pyprojects_derived_from_workspace() -> None:
    # Derived from [tool.uv.workspace].members, not a hand-maintained list, so a
    # new member cannot skip sibling-dependency pinning.
    assert _bump.PACKAGE_PYPROJECTS
    for path in _bump.PACKAGE_PYPROJECTS:
        assert path.exists()


def test_init_paths_derived_from_hatch_config() -> None:
    # Derived from each package's [tool.hatch.version].path, not a hardcoded
    # list, so a new member's __version__ file is bumped and verified too.
    assert len(_bump.INIT_PATHS) == len(_bump.PACKAGE_PYPROJECTS)
    for path in _bump.INIT_PATHS:
        assert path.exists()
        assert path.name == "__init__.py"


def test_read_sdk_version_locates_sdk_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A non-SDK package is listed first; read_sdk_version must still find pipefy
    # by name rather than trusting member order.
    def _pkg(name: str, version: str) -> Path:
        (tmp_path / name / "src").mkdir(parents=True)
        (tmp_path / name / "src" / "__init__.py").write_text(
            f'__version__ = "{version}"\n', encoding="utf-8"
        )
        pyproject = tmp_path / name / "pyproject.toml"
        pyproject.write_text(
            f'[project]\nname = "{name}"\nversion = "0.0.0"\n'
            '[tool.hatch.version]\npath = "src/__init__.py"\n',
            encoding="utf-8",
        )
        return pyproject

    auth = _pkg("pipefy-auth", "1.1.1")
    sdk = _pkg("pipefy", "2.2.2")
    monkeypatch.setattr(_bump, "PACKAGE_PYPROJECTS", (auth, sdk))

    assert _bump.read_sdk_version() == "2.2.2"


def test_declared_sibling_deps_keeps_only_workspace_members(tmp_path: Path) -> None:
    members = {"pipefy", "pipefy-auth", "pipefy-infra"}
    pyproject = tmp_path / "pyproject.toml"
    _write_pkg(
        pyproject,
        "pipefy-cli",
        ("pipefy==0.3.0-alpha.1", "pipefy-auth==0.3.0-alpha.1", "typer>=0.12"),
    )
    assert _bump.declared_sibling_deps(pyproject, members) == {"pipefy", "pipefy-auth"}


def test_write_dep_pins_pins_declared_siblings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The set to pin is derived from each package's real dependencies: the
    # sibling `pipefy` gets pinned (even though it was unpinned), the non-member
    # `typer` is left alone, and no hand-maintained map is consulted.
    sdk = tmp_path / "sdk.toml"
    cli = tmp_path / "cli.toml"
    _write_pkg(sdk, "pipefy", ())
    _write_pkg(cli, "pipefy-cli", ("pipefy", "typer>=0.12"))
    monkeypatch.setattr(_bump, "PACKAGE_PYPROJECTS", (sdk, cli))

    _bump.write_dep_pins("9.9.9")

    cli_text = cli.read_text(encoding="utf-8")
    assert '"pipefy==9.9.9"' in cli_text
    assert '"typer>=0.12"' in cli_text
