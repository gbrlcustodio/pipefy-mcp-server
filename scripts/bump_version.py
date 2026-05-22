#!/usr/bin/env python3
"""Bump the lockstep workspace version across SDK, MCP, CLI, Auth, and root workspace meta."""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_PYPROJECT = REPO_ROOT / "pyproject.toml"
INIT_PATHS = (
    REPO_ROOT / "packages/sdk/src/pipefy_sdk/__init__.py",
    REPO_ROOT / "packages/mcp/src/pipefy_mcp/__init__.py",
    REPO_ROOT / "packages/cli/src/pipefy_cli/__init__.py",
    REPO_ROOT / "packages/auth/src/pipefy_auth/__init__.py",
)

ROOT_PROJECT_VERSION_RE = re.compile(
    r"^(version\s*=\s*)[\"'][^\"']+[\"']",
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


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage: bump_version.py <major|minor|patch|prerelease|version=X.Y.Z>",
            file=sys.stderr,
        )
        return 2

    token = sys.argv[1]
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
            "Use major, minor, patch, prerelease, or version=X.Y.Z",
            file=sys.stderr,
        )
        return 2

    write_version_to_all_files(new_version)
    print(f"Bumped {current} -> {new_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
