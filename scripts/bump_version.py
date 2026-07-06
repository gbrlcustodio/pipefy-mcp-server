#!/usr/bin/env python3
"""Bump the lockstep workspace version across SDK, MCP, CLI, Auth, Infra, the Claude plugin manifest, and root workspace meta.

After rewriting the version strings, runs ``uv lock`` so the workspace
lockfile's ``pipefy-workspace`` entry tracks the new version.

The ``verify`` mode reads every version-bearing file and exits non-zero on
mismatch; CI invokes this in place of an inline lockstep snippet so the
writer and reader stay in one place.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from collections.abc import Callable, Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_PYPROJECT = REPO_ROOT / "pyproject.toml"
PLUGIN_MANIFEST = REPO_ROOT / ".claude-plugin/plugin.json"

# The SDK distribution; its __version__ is the lockstep source of truth every
# other version-bearing file is compared against.
SDK_DIST_NAME = "pipefy"


def _load_toml(path: Path) -> dict:
    """Parse a TOML file into a dict."""
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _workspace_pyprojects() -> tuple[Path, ...]:
    """Resolve package pyproject paths from the root ``[tool.uv.workspace]`` members.

    uv is the source of truth for workspace membership: a package it does not
    know about is never built, locked, or published. Deriving from that list
    (rather than a second hand-maintained copy) means adding a member cannot
    silently escape sibling-dependency pinning or version bumping. Members may
    be literal paths or globs (``packages/*``); both resolve here.
    """
    members = _load_toml(ROOT_PYPROJECT)["tool"]["uv"]["workspace"]["members"]
    paths: list[Path] = []
    for pattern in members:
        paths.extend(sorted(REPO_ROOT.glob(f"{pattern}/pyproject.toml")))
    return tuple(paths)


# Every workspace package, derived from uv's member list. The bump writer and
# the verifier both read each package's declared workspace-sibling dependencies
# from here (see declared_sibling_deps), so pinning follows the real dependency
# lists with no hand-maintained pin map to keep in sync.
PACKAGE_PYPROJECTS: tuple[Path, ...] = _workspace_pyprojects()


def _hatch_version_path(pyproject: Path) -> Path:
    """Resolve a package's ``__version__`` file from its ``[tool.hatch.version]`` path.

    hatch already declares which file holds the version (``path`` under
    ``[tool.hatch.version]``, relative to the package directory), so deriving
    from it keeps the version files in step with the packages, no second list.
    """
    rel = _load_toml(pyproject)["tool"]["hatch"]["version"]["path"]
    return pyproject.parent / rel


# Each package's __version__ file, derived from hatch's version-path config so a
# new workspace member is bumped and verified without editing a hardcoded list.
INIT_PATHS: tuple[Path, ...] = tuple(_hatch_version_path(p) for p in PACKAGE_PYPROJECTS)

# Anchored to the [project] table. The middle alternation walks lines that
# don't start with `[` (so a sibling [tool.X] header ends the run), but the
# line CONTENTS can contain `[` (so `classifiers = [...]`, `dependencies =
# [...]`, etc. above `version` don't break the match).
ROOT_PROJECT_VERSION_RE = re.compile(
    r"^(\[project\]\s*$"
    r"(?:\n(?!\[)[^\n]*)*?"
    r"\nversion\s*=\s*)"
    r"[\"'][^\"']+[\"']",
    re.MULTILINE,
)

VERSION_ASSIGN_RE = re.compile(
    r'^(__version__\s*=\s*)["\']([^"\']+)["\']',
    re.MULTILINE,
)

# The Claude plugin manifest carries the release version too (it is what the
# marketplace shows), so it moves with every bump. plugin.json has a single
# top-level "version" key.
PLUGIN_MANIFEST_VERSION_RE = re.compile(
    r'(?P<prefix>"version"\s*:\s*")(?P<value>[^"]+)(?P<suffix>")',
)

CORE_VER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")
PRERELEASE_SUFFIX_RE = re.compile(
    r"^(a|alpha|b|beta|rc)\.?(\d+)$",
    re.IGNORECASE,
)


def _sole_match(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    """Return the single match of ``pattern`` in ``text``, or ``None`` for zero or many.

    The tokens this script reads (a package's ``__version__``, a quoted sibling
    dependency) must be unique in their file. Resolving to the first hit would
    let a decoy (a second ``__version__`` line, the same dep quoted in a
    dependency group) be silently read; treating "more than one" as no match
    surfaces it as a failure instead.
    """
    matches = pattern.finditer(text)
    first = next(matches, None)
    if first is None or next(matches, None) is not None:
        return None
    return first


def _sub_exactly_one(
    pattern: re.Pattern[str], repl: str, text: str, *, what: str, where: Path
) -> str:
    """Substitute the one expected match of ``pattern`` in ``text``; raise otherwise.

    The write-side twin of ``_sole_match``: replacing every match and asserting
    the count is exactly one means a decoy occurrence fails loudly instead of
    being silently rewritten (first hit) or left behind.
    """
    new_text, count = pattern.subn(repl, text)
    if count != 1:
        msg = f"Expected one {what} in {where}, replaced {count}"
        raise ValueError(msg)
    return new_text


def _sdk_pyproject() -> Path:
    """The SDK package pyproject, located by distribution name, not position.

    Workspace member order is not guaranteed (a ``packages/*`` glob sorts
    alphabetically), so the source-of-truth package is found by name, matched
    with the same canonicalization the sibling-dependency checks use.
    """
    from packaging.utils import canonicalize_name

    target = canonicalize_name(SDK_DIST_NAME)
    for pyproject in PACKAGE_PYPROJECTS:
        if canonicalize_name(_load_toml(pyproject)["project"]["name"]) == target:
            return pyproject
    msg = f"workspace has no {SDK_DIST_NAME!r} package"
    raise ValueError(msg)


def read_sdk_version() -> str:
    """Return the current ``__version__`` from the SDK package (source of truth)."""
    path = _hatch_version_path(_sdk_pyproject())
    text = path.read_text(encoding="utf-8")
    m = _sole_match(VERSION_ASSIGN_RE, text)
    if not m:
        msg = f"Expected exactly one __version__ assignment in {path}"
        raise ValueError(msg)
    return m.group(2)


def write_version_to_all_files(new_version: str) -> None:
    """Replace ``__version__`` in each package ``__init__.py`` and root workspace meta."""
    for path in INIT_PATHS:
        text = path.read_text(encoding="utf-8")
        new_text = _sub_exactly_one(
            VERSION_ASSIGN_RE,
            rf'\1"{new_version}"',
            text,
            what="__version__ assignment",
            where=path,
        )
        path.write_text(new_text, encoding="utf-8")

    root_text = ROOT_PYPROJECT.read_text(encoding="utf-8")
    new_root = _sub_exactly_one(
        ROOT_PROJECT_VERSION_RE,
        rf'\1"{new_version}"',
        root_text,
        what="[project] version assignment",
        where=ROOT_PYPROJECT,
    )
    ROOT_PYPROJECT.write_text(new_root, encoding="utf-8")

    manifest_text = PLUGIN_MANIFEST.read_text(encoding="utf-8")
    new_manifest = _sub_exactly_one(
        PLUGIN_MANIFEST_VERSION_RE,
        rf"\g<prefix>{new_version}\g<suffix>",
        manifest_text,
        what='"version" key',
        where=PLUGIN_MANIFEST,
    )
    PLUGIN_MANIFEST.write_text(new_manifest, encoding="utf-8")


def workspace_dep_pin_re(dep_name: str) -> re.Pattern[str]:
    """Match a quoted ``dep_name`` requirement; group 2 captures its ``==`` pin.

    Group 2 is the pinned version, or ``None`` when the requirement is unpinned
    (``"pipefy"``), so this one pattern serves both the writer (rewrites the
    pin) and the verifier (reads it, treating ``None`` as unpinned).

    The name must fill the entire quoted string, so an unquoted
    ``[tool.uv.sources]`` key (``pipefy = { workspace = true }``) and a bare
    mention inside a description are not matched, and ``pipefy`` does not match
    ``"pipefy-infra"`` (the closing quote must follow immediately). A package's
    own ``name = "..."`` field IS a full quoted string and would match; that
    collision cannot arise because the pinned names come from a package's own
    ``[project.dependencies]``, which never lists itself.
    """
    return re.compile(rf'(["\']){re.escape(dep_name)}(?:\s*==([^"\']*))?\1')


def write_dep_pins(new_version: str) -> None:
    """Pin every workspace-sibling dependency each package declares to ``new_version``.

    Each published package pins its workspace siblings to the exact lockstep
    version in its built metadata, so ``pip install pipefy-cli==X`` pulls its
    siblings at X rather than a newer sibling that happens to be on PyPI (the
    ``[tool.uv.sources]`` workspace mapping overrides these pins for in-repo
    dev). The set to pin is derived from each package's real
    ``[project.dependencies]``, so a newly added inter-package dependency is
    pinned automatically with no hand-maintained list to update.
    """
    for path, deps in _packages_with_sibling_deps():
        text = path.read_text(encoding="utf-8")
        for dep in deps:
            text = _sub_exactly_one(
                workspace_dep_pin_re(dep),
                rf"\g<1>{dep}=={new_version}\g<1>",
                text,
                what=f"{dep!r} dependency",
                where=path,
            )
        path.write_text(text, encoding="utf-8")


def workspace_members() -> set[str]:
    """Canonical distribution names of every workspace package."""
    from packaging.utils import canonicalize_name

    return {
        canonicalize_name(_load_toml(path)["project"]["name"])
        for path in PACKAGE_PYPROJECTS
    }


def declared_sibling_deps(path: Path, members: set[str]) -> set[str]:
    """Names of the workspace siblings a package's ``[project]`` depends on.

    Reads ``[project.dependencies]`` and keeps the requirements whose
    canonicalized name is another workspace member. Returns the names as
    written in the file, so callers can match them against the raw dependency
    text; a package never depends on itself, so its own name is never returned.
    """
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    deps = _load_toml(path).get("project", {}).get("dependencies", [])
    return {
        req.name
        for spec in deps
        if canonicalize_name((req := Requirement(spec)).name) in members
    }


def _packages_with_sibling_deps() -> Iterator[tuple[Path, list[str]]]:
    """Yield each package and its declared workspace-sibling deps, skipping none.

    Shared by the pin writer and the verifier so both walk the workspace and
    resolve siblings the same way.
    """
    members = workspace_members()
    for path in PACKAGE_PYPROJECTS:
        deps = sorted(declared_sibling_deps(path, members))
        if deps:
            yield path, deps


def parse_core(version: str) -> tuple[int, int, int]:
    """Parse leading ``X.Y.Z`` from a version string."""
    m = CORE_VER_RE.match(version.strip())
    if not m:
        msg = f"Version must start with MAJOR.MINOR.PATCH, got {version!r}"
        raise ValueError(msg)
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def suffix_after_core(version: str) -> str:
    """Return the substring after ``X.Y.Z`` (e.g. ``a1``, ``rc2``), or empty."""
    m = CORE_VER_RE.match(version.strip())
    if not m:
        msg = f"Version must start with MAJOR.MINOR.PATCH, got {version!r}"
        raise ValueError(msg)
    return version.strip()[m.end() :]


def bump_major(current: str) -> str:
    x, y, z = parse_core(current)
    return f"{x + 1}.0.0"


def bump_minor(current: str) -> str:
    x, y, z = parse_core(current)
    return f"{x}.{y + 1}.0"


def bump_patch(current: str) -> str:
    x, y, z = parse_core(current)
    return f"{x}.{y}.{z + 1}"


def _format_prerelease_suffix(kind: str, n: int, original_rest: str) -> str:
    """Format the suffix after ``X.Y.Z``, preserving SemVer-style when present."""
    kind_lower = kind.lower()
    if kind_lower in ("alpha", "a"):
        short, long = "a", "alpha"
    elif kind_lower in ("beta", "b"):
        short, long = "b", "beta"
    else:
        short, long = "rc", "rc"

    if re.match(rf"^[-_.]({long}|{short})\.\d+$", original_rest, re.IGNORECASE):
        separator = original_rest[0]
        return f"{separator}{long}.{n}"

    return f"{short}{n}"


def bump_prerelease(current: str) -> str:
    """Increment or introduce a pre-release suffix (``aN`` / ``bN`` / ``rcN`` or ``-beta.N``).

    When the current version has no suffix (e.g. ``0.1.0``), the next value is the first alpha
    of the *next* patch (e.g. ``0.1.1a1``), not an alpha of the same patch.
    """
    x, y, z = parse_core(current)
    rest = suffix_after_core(current)
    if not rest:
        return f"{x}.{y}.{z + 1}a1"
    rest_norm = rest.lstrip("._-")
    m = PRERELEASE_SUFFIX_RE.match(rest_norm)
    if not m:
        msg = (
            f"Cannot bump prerelease: unrecognized suffix {rest_norm!r} on {current!r}"
        )
        raise ValueError(msg)
    kind, num_s = m.groups()
    n = int(num_s) + 1
    return f"{x}.{y}.{z}{_format_prerelease_suffix(kind, n, rest)}"


def parse_explicit_version(arg: str) -> str:
    """Parse ``version=X.Y.Z`` (optional leading ``v`` on the version)."""
    lowered = arg.lower()
    if not lowered.startswith("version="):
        msg = f"Expected version=X.Y.Z, got {arg!r}"
        raise ValueError(msg)
    raw = arg[len("version=") :].strip()
    if raw.startswith("v") or raw.startswith("V"):
        raw = raw[1:]
    parse_core(raw)
    return raw


def refresh_lockfile() -> None:
    """Run ``uv lock`` so the workspace lockfile picks up the new version.

    Without this, ``uv.lock``'s ``pipefy-workspace`` entry lags behind the
    root ``pyproject.toml`` and CI's ``uv sync --locked`` fails on every PR
    until someone runs ``uv lock`` by hand.
    """
    print("Refreshing uv.lock...")
    subprocess.run(["uv", "lock"], cwd=REPO_ROOT, check=True)


def read_root_pyproject_version() -> str:
    """Return ``[project].version`` from the root pyproject.toml."""
    return _load_toml(ROOT_PYPROJECT)["project"]["version"]


def read_uv_lock_workspace_version() -> str:
    """Return the ``pipefy-workspace`` package version from uv.lock.

    The value is whatever uv wrote, which is PEP 440-normalized (e.g. uv
    stores ``0.2.0b2.dev1`` for a pyproject value of ``0.2.0-beta.2.dev1``).
    Callers must normalize the comparison side, not this one.
    """
    data = _load_toml(REPO_ROOT / "uv.lock")
    for pkg in data.get("package", []):
        if pkg.get("name") == "pipefy-workspace":
            return pkg["version"]
    raise KeyError("pipefy-workspace not found in uv.lock")


def verify_lockstep() -> int:
    """Assert every version-bearing file holds the same version; print mismatches.

    The version-bearing files include each package's declared workspace-sibling
    ``==`` pins, so an unpinned sibling dependency fails here too. Returns 0 on
    success, 1 on any mismatch or missing field. Compares canonical PEP 440
    forms via ``packaging.version.Version`` so the pyproject string
    ``0.2.0-beta.2.dev1`` matches uv.lock's normalized ``0.2.0b2.dev1``.
    """
    from packaging.version import Version

    raw: dict[str, str] = {}
    for path in INIT_PATHS:
        text = path.read_text(encoding="utf-8")
        m = _sole_match(VERSION_ASSIGN_RE, text)
        if not m:
            print(f"expected exactly one __version__ in {path}", file=sys.stderr)
            return 1
        raw[str(path.relative_to(REPO_ROOT))] = m.group(2)

    for path, deps in _packages_with_sibling_deps():
        text = path.read_text(encoding="utf-8")
        for dep in deps:
            m = _sole_match(workspace_dep_pin_re(dep), text)
            if not m or m.group(2) is None:
                print(
                    f"missing or ambiguous pinned {dep!r} dependency in {path}",
                    file=sys.stderr,
                )
                return 1
            raw[f"{path.relative_to(REPO_ROOT)}::{dep}"] = m.group(2)

    try:
        raw["pyproject.toml"] = read_root_pyproject_version()
    except (KeyError, tomllib.TOMLDecodeError, OSError) as exc:
        print(
            f"could not read [project].version from pyproject.toml: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        raw["uv.lock"] = read_uv_lock_workspace_version()
    except (KeyError, tomllib.TOMLDecodeError, OSError) as exc:
        print(
            f"could not read pipefy-workspace version from uv.lock: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        manifest_text = PLUGIN_MANIFEST.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"could not read {PLUGIN_MANIFEST}: {exc}", file=sys.stderr)
        return 1
    m = _sole_match(PLUGIN_MANIFEST_VERSION_RE, manifest_text)
    if not m:
        print(f'expected exactly one "version" in {PLUGIN_MANIFEST}', file=sys.stderr)
        return 1
    raw[str(PLUGIN_MANIFEST.relative_to(REPO_ROOT))] = m.group("value")

    canonical = {label: str(Version(v)) for label, v in raw.items()}
    if len(set(canonical.values())) != 1:
        print(f"version mismatch across packages: {raw}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage: bump_version.py <major|minor|patch|prerelease|version=X.Y.Z|verify>",
            file=sys.stderr,
        )
        return 2

    token = sys.argv[1]
    if token == "verify":
        return verify_lockstep()

    current = read_sdk_version()

    bumpers: dict[str, Callable[[str], str]] = {
        "major": bump_major,
        "minor": bump_minor,
        "patch": bump_patch,
        "prerelease": bump_prerelease,
    }

    if token.lower().startswith("version="):
        new_version = parse_explicit_version(token)
    elif token in bumpers:
        new_version = bumpers[token](current)
    else:
        print(
            f"Unknown argument {token!r}. "
            "Use major, minor, patch, prerelease, version=X.Y.Z, or verify",
            file=sys.stderr,
        )
        return 2

    write_version_to_all_files(new_version)
    write_dep_pins(new_version)
    refresh_lockfile()
    print(f"Bumped {current} -> {new_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
