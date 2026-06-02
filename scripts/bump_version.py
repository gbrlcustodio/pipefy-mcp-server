#!/usr/bin/env python3
"""Bump the lockstep workspace version across SDK, MCP, CLI, Auth, Infra, and root workspace meta.

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
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_PYPROJECT = REPO_ROOT / "pyproject.toml"
INIT_PATHS = (
    REPO_ROOT / "packages/sdk/src/pipefy_sdk/__init__.py",
    REPO_ROOT / "packages/mcp/src/pipefy_mcp/__init__.py",
    REPO_ROOT / "packages/cli/src/pipefy_cli/__init__.py",
    REPO_ROOT / "packages/auth/src/pipefy_auth/__init__.py",
    REPO_ROOT / "packages/infra/src/pipefy_infra/__init__.py",
)

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

CORE_VER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")
PRERELEASE_SUFFIX_RE = re.compile(
    r"^(a|alpha|b|beta|rc)\.?(\d+)$",
    re.IGNORECASE,
)


def read_sdk_version() -> str:
    """Return the current ``__version__`` from the SDK package (source of truth)."""
    text = INIT_PATHS[0].read_text(encoding="utf-8")
    m = VERSION_ASSIGN_RE.search(text)
    if not m:
        msg = f"No __version__ assignment found in {INIT_PATHS[0]}"
        raise ValueError(msg)
    return m.group(2)


def write_version_to_all_files(new_version: str) -> None:
    """Replace ``__version__`` in each package ``__init__.py`` and root workspace meta."""
    for path in INIT_PATHS:
        text = path.read_text(encoding="utf-8")
        new_text, count = VERSION_ASSIGN_RE.subn(
            rf'\1"{new_version}"',
            text,
            count=1,
        )
        if count != 1:
            msg = f"Expected one __version__ assignment in {path}, replaced {count}"
            raise ValueError(msg)
        path.write_text(new_text, encoding="utf-8")

    root_text = ROOT_PYPROJECT.read_text(encoding="utf-8")
    new_root, root_count = ROOT_PROJECT_VERSION_RE.subn(
        rf'\1"{new_version}"',
        root_text,
        count=1,
    )
    if root_count != 1:
        msg = (
            f"Expected one [project] version assignment in {ROOT_PYPROJECT}, "
            f"replaced {root_count}"
        )
        raise ValueError(msg)
    ROOT_PYPROJECT.write_text(new_root, encoding="utf-8")


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
    data = tomllib.loads(ROOT_PYPROJECT.read_text(encoding="utf-8"))
    return data["project"]["version"]


def read_uv_lock_workspace_version() -> str:
    """Return the ``pipefy-workspace`` package version from uv.lock.

    The value is whatever uv wrote, which is PEP 440-normalized (e.g. uv
    stores ``0.2.0b2.dev1`` for a pyproject value of ``0.2.0-beta.2.dev1``).
    Callers must normalize the comparison side, not this one.
    """
    data = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    for pkg in data.get("package", []):
        if pkg.get("name") == "pipefy-workspace":
            return pkg["version"]
    raise KeyError("pipefy-workspace not found in uv.lock")


def verify_lockstep() -> int:
    """Assert every version-bearing file holds the same version; print mismatches.

    Returns 0 on success, 1 on any mismatch or missing field. Compares
    canonical PEP 440 forms via ``packaging.version.Version`` so the
    pyproject string ``0.2.0-beta.2.dev1`` matches uv.lock's normalized
    ``0.2.0b2.dev1``.
    """
    from packaging.version import Version

    raw: dict[str, str] = {}
    for path in INIT_PATHS:
        text = path.read_text(encoding="utf-8")
        m = VERSION_ASSIGN_RE.search(text)
        if not m:
            print(f"missing __version__ in {path}", file=sys.stderr)
            return 1
        raw[str(path.relative_to(REPO_ROOT))] = m.group(2)

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
    refresh_lockfile()
    print(f"Bumped {current} -> {new_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
