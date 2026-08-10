#!/usr/bin/env python3
"""Prove ``install.sh`` then ``uninstall.sh`` leaves ``HOME`` where it started.

Every other check in this repository tests a step someone thought to write.
This one compares the filesystem before the install, after it, and after the
teardown, so a path a new installer step creates has to be removed by the
teardown or show up here — nobody has to have predicted it.

Three snapshots, because two would pass on a machine where nothing installed:
the middle one is what makes the comparison mean anything.

Usage:
    check_roundtrip.py snapshot <out>
    check_roundtrip.py check <before> <installed> <after>
"""

from __future__ import annotations

import fnmatch
import os
import sys
from pathlib import Path

HOME = Path(os.path.expanduser("~"))

# Directories that hold nothing this toolkit owns. Not descended into, so the
# comparison stays fast and its output stays readable.
PRUNE = {
    ".cache": "uv's and npm's caches; the uv cache is reported and never cleared, "
    "because uv hardlinks tool environments into it",
    ".npm": "npm's package cache, populated by 'npx skills add'",
    ".local/share/uv": "uv's own data root: managed interpreters and the tool "
    "directory. 'uv tool uninstall' empties this toolkit's environments and the "
    "root belongs to uv",
    ".git": "not present under HOME on a runner, and never toolkit state",
}

# Files a completed teardown deliberately leaves behind. Each is a decision.
ALLOWED = (
    (
        ".local/bin/uv",
        "uv itself is never removed: by now other tools depend on it, and a tool "
        "directory is not uv",
    ),
    (".local/bin/uvx", "the same binary under its second name"),
    (
        ".local/bin/env",
        "the PATH snippet uv's installer writes, alongside the shell rc lines it "
        "edits; both are left for the same reason uv is",
    ),
    (".local/bin/env.fish", "the fish form of that snippet"),
    (
        ".cursor/mcp.json",
        "the client's own config file. The teardown removes the registration it "
        "made and leaves the file, which by teardown time may hold other servers",
    ),
    (
        "*.bak.[0-9]*",
        "the copy taken before editing a file the user owns; deleting it would "
        "defeat the point of taking it",
    ),
    (
        ".bashrc",
        "shell rc files: uv's installer appends a PATH line and the teardown "
        "leaves it, since uv stays",
    ),
    (".profile", "the same"),
    (".zshrc", "the same"),
    (".bash_profile", "the same"),
)

# Evidence that the install in the middle actually happened. Without it a
# teardown that removed nothing would compare equal and pass.
INSTALLED = (
    ".local/bin/pipefy",
    ".local/bin/pipefy-mcp-server",
    ".local/state/pipefy/install-receipt",
    ".cursor/mcp.json",
)


def snapshot(out: Path) -> int:
    seen = []
    for root, dirs, files in os.walk(HOME):
        rel = Path(root).relative_to(HOME)
        prefix = "" if rel == Path(".") else f"{rel}/"
        dirs[:] = [d for d in dirs if prefix + d not in PRUNE]
        seen.extend(prefix + name for name in files)
    out.write_text("\n".join(sorted(seen)) + "\n", encoding="utf-8")
    print(f"{len(seen)} files under {HOME}")
    return 0


def _read(path: Path) -> set[str]:
    return {line for line in path.read_text(encoding="utf-8").splitlines() if line}


def _reason(path: str) -> str | None:
    for pattern, reason in ALLOWED:
        if path == pattern or fnmatch.fnmatch(path, pattern):
            return reason
    return None


def check(before: Path, installed: Path, after: Path) -> int:
    was, mid, now = _read(before), _read(installed), _read(after)

    missing = [path for path in INSTALLED if path not in mid]
    if missing:
        print("The install left no trace of:", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        print(
            "Nothing was torn down, so the comparison proves nothing.", file=sys.stderr
        )
        return 1

    unexplained = {}
    for path in sorted(now - was):
        reason = _reason(path)
        if reason is None:
            unexplained[path] = None
        else:
            print(f"  left on purpose: {path}\n      {reason}")

    if unexplained:
        print("\ninstall.sh created these and uninstall.sh left them:", file=sys.stderr)
        for path in unexplained:
            print(f"  {path}", file=sys.stderr)
        return 1

    vanished = sorted(was - now)
    if vanished:
        print("\nuninstall.sh removed files that predate the install:", file=sys.stderr)
        for path in vanished:
            print(f"  {path}", file=sys.stderr)
        return 1

    print(f"\nRound trip clean: {len(mid - was)} files installed, all accounted for.")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "snapshot":
        return snapshot(Path(argv[2]))
    if len(argv) == 5 and argv[1] == "check":
        return check(Path(argv[2]), Path(argv[3]), Path(argv[4]))
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
