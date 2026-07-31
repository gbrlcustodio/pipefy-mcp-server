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
def test_json_version_re_replaces_version(manifest: str) -> None:
    new_text, count = _bump.JSON_VERSION_RE.subn(
        r"\g<prefix>9.9.9\g<suffix>", manifest, count=1
    )
    assert count == 1
    assert '"version"' in new_text and "9.9.9" in new_text
    # The name key must not be rewritten.
    assert '"pipefy"' in new_text


@pytest.mark.parametrize(
    "manifest", [_bump.PLUGIN_MANIFEST, _bump.MARKETPLACE_MANIFEST]
)
def test_json_manifest_version_matches_real_manifest(manifest: Path) -> None:
    # Both Claude manifests carry the lockstep version; a lone "version" key must
    # resolve and equal the SDK source of truth.
    text = manifest.read_text(encoding="utf-8")
    m = _bump._sole_match(_bump.JSON_VERSION_RE, text)
    assert m is not None
    assert m.group("value") == _bump.read_sdk_version()


def test_json_manifests_cover_every_versioned_plugin_manifest() -> None:
    # A .claude-plugin JSON that carries a "version" but is absent from
    # JSON_MANIFESTS is exactly the drift this fix targets: it exists yet is
    # bumped and verified by nothing. Deriving the expected set from the tree
    # (not a hand-list) means neither dropping a manifest nor adding a future one
    # can silently unwire it.
    versioned = {
        path
        for path in (_bump.REPO_ROOT / ".claude-plugin").glob("*.json")
        if _bump.JSON_VERSION_RE.search(path.read_text(encoding="utf-8"))
    }
    assert versioned == set(_bump.JSON_MANIFESTS)


def test_write_json_manifest_version_rewrites_marketplace_entry(tmp_path: Path) -> None:
    # The marketplace manifest holds the version on a nested plugin entry; the
    # writer must rewrite it and leave the surrounding keys untouched.
    manifest = tmp_path / "marketplace.json"
    manifest.write_text(
        '{\n  "name": "pipefy",\n  "plugins": [\n    {\n'
        '      "name": "pipefy",\n      "version": "0.2.0-beta.1"\n    }\n  ]\n}\n',
        encoding="utf-8",
    )

    _bump._write_json_manifest_version(manifest, "9.9.9")

    text = manifest.read_text(encoding="utf-8")
    assert '"version": "9.9.9"' in text
    assert '"name": "pipefy"' in text


def test_write_json_manifest_version_rejects_ambiguous_version(tmp_path: Path) -> None:
    # A second "version" key (e.g. a further catalog entry) must fail loudly
    # rather than have only the first rewritten.
    manifest = tmp_path / "marketplace.json"
    manifest.write_text(
        '{\n  "plugins": [\n'
        '    { "version": "0.1.0" },\n    { "version": "0.1.0" }\n  ]\n}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match='Expected one "version" key'):
        _bump._write_json_manifest_version(manifest, "9.9.9")


def _write_pkg(path: Path, name: str, deps: tuple[str, ...]) -> None:
    dep_lines = "".join(f'    "{d}",\n' for d in deps)
    path.write_text(
        f'[project]\nname = "{name}"\nversion = "0.1.0"\n'
        f"dependencies = [\n{dep_lines}]\n",
        encoding="utf-8",
    )


def _write_hatch_pkg(root: Path, name: str, init_body: str) -> Path:
    """Write a hatch package (src/__init__.py + pyproject) under root/name.

    Returns the pyproject path. Used by tests that exercise version reading via
    the [tool.hatch.version] path.
    """
    (root / name / "src").mkdir(parents=True)
    (root / name / "src" / "__init__.py").write_text(init_body, encoding="utf-8")
    pyproject = root / name / "pyproject.toml"
    pyproject.write_text(
        f'[project]\nname = "{name}"\nversion = "0.0.0"\n'
        '[tool.hatch.version]\npath = "src/__init__.py"\n',
        encoding="utf-8",
    )
    return pyproject


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
    auth = _write_hatch_pkg(tmp_path, "pipefy-auth", '__version__ = "1.1.1"\n')
    sdk = _write_hatch_pkg(tmp_path, "pipefy", '__version__ = "2.2.2"\n')
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


def test_sole_match_treats_zero_or_many_as_no_match() -> None:
    pat = _bump.VERSION_ASSIGN_RE
    assert _bump._sole_match(pat, "") is None
    assert _bump._sole_match(pat, '__version__ = "1.0.0"\n').group(2) == "1.0.0"
    two = '__version__ = "1.0.0"\n__version__ = "2.0.0"\n'
    assert _bump._sole_match(pat, two) is None


def test_read_sdk_version_rejects_duplicate_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A decoy second __version__ (e.g. in a docstring example) must fail loudly,
    # not resolve to the first hit.
    pyproject = _write_hatch_pkg(
        tmp_path, "pipefy", '__version__ = "1.0.0"\n__version__ = "2.0.0"\n'
    )
    monkeypatch.setattr(_bump, "PACKAGE_PYPROJECTS", (pyproject,))

    with pytest.raises(ValueError, match="Expected exactly one __version__"):
        _bump.read_sdk_version()


def test_write_dep_pins_rejects_duplicate_dep_occurrence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `pipefy` is quoted in both [project.dependencies] and a dependency group;
    # pinning the first and leaving the other would drift, so it must fail.
    sdk = tmp_path / "sdk.toml"
    cli = tmp_path / "cli.toml"
    _write_pkg(sdk, "pipefy", ())
    cli.write_text(
        '[project]\nname = "pipefy-cli"\nversion = "0.1.0"\n'
        'dependencies = ["pipefy"]\n'
        '[dependency-groups]\ndev = ["pipefy==0.0.0"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(_bump, "PACKAGE_PYPROJECTS", (sdk, cli))

    with pytest.raises(ValueError, match="Expected one 'pipefy' dependency"):
        _bump.write_dep_pins("9.9.9")


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("0.5.0-alpha.1", "alpha"),
        ("0.5.0a1", "alpha"),
        ("0.5.0-beta.2", "beta"),
        ("0.5.0b2", "beta"),
        ("0.5.0-rc.1", "rc"),
        ("0.5.0rc1", "rc"),
        ("0.5.0", None),
        ("1.0.0", None),
    ],
)
def test_prerelease_track_ignores_spelling(version: str, expected: str | None) -> None:
    # The branch gate in release.py keys off this, so the SemVer-style and the
    # compact PEP 440 form must classify identically.
    assert _bump.prerelease_track(version) == expected


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        # Promotion keeps X.Y.Z and resets the counter, preserving the style.
        ("0.5.0-alpha.1", "0.5.0-beta.1"),
        ("0.5.0-alpha.7", "0.5.0-beta.1"),
        ("0.5.0a3", "0.5.0b1"),
        ("1.0.0.alpha.2", "1.0.0.beta.1"),
    ],
)
def test_bump_beta_promotes_alpha_to_first_beta(current: str, expected: str) -> None:
    assert _bump.bump_beta(current) == expected


def test_bump_beta_promotion_is_an_upgrade() -> None:
    # PEP 440 must order the promotion upward, or release_pr's ahead-of-main
    # guard would reject its own output.
    from packaging.version import Version

    assert Version(_bump.bump_beta("0.5.0-alpha.3")) > Version("0.5.0-alpha.3")


@pytest.mark.parametrize("current", ["0.5.0-beta.1", "0.5.0-rc.1", "0.5.0"])
def test_bump_beta_refuses_non_alpha(current: str) -> None:
    # Only alphas promote; walking a beta line is `prerelease`, and opening a
    # new line is an explicit `version=`, so no core bump is implied here.
    with pytest.raises(ValueError, match="not an alpha"):
        _bump.bump_beta(current)
