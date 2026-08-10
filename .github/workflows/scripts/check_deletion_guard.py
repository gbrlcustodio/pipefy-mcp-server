#!/usr/bin/env python3
"""Every deletion in ``uninstall.sh`` has to route through ``remove_path``.

``remove_path`` refuses an empty argument, a relative path, ``/`` and ``$HOME``
exactly. Those refusals are worth nothing if a later edit reaches for ``rm``
directly, and a reviewer cannot see an indirection that is missing. This
asserts the shape instead: the only ``rm`` and ``rmdir`` in command position
live inside ``remove_path``, apart from the exit trap listed below, and the
refusals are still there.

Usage: check_deletion_guard.py [path/to/uninstall.sh]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# The trap runs on a signal, when the script may be part-way through anything.
# `remove_path` reports through `err`, which exits, and honours --dry-run,
# which would leak these; both are wrong for a cleanup handler. The paths are
# this script's own mktemp results and never come from the scan.
ALLOWED = frozenset({"""trap 'rm -f "$RECORDS" "$PLAN" "$NOTES"' EXIT INT TERM"""})

# `rm` / `rmdir` in command position: at the start of a line, or after a
# separator, a keyword, or the `run` wrapper. A `rmdir)` case label is a
# pattern rather than a command.
DELETION = re.compile(
    r"(?:^|[;&|(]|\b(?:then|else|elif|do|run|exec|eval)\s+)\s*(?:rm|rmdir)\b(?!\s*\))"
)

REFUSALS = (
    'err "refusing to remove an empty path"',
    'err "refusing to remove a relative path: $_rp"',
    'err "refusing to remove /"',
    'err "refusing to remove \\$HOME ($HOME)"',
)


def _function_body(lines: list[str], name: str, script: Path) -> range:
    """Line numbers of ``name``'s body, from its opening brace to the closing one."""
    start = next(
        (i for i, line in enumerate(lines) if line.startswith(f"{name}() {{")), None
    )
    if start is None:
        raise SystemExit(f"{script.name}: {name}() not found")
    end = next((i for i in range(start + 1, len(lines)) if lines[i] == "}"), None)
    if end is None:
        raise SystemExit(f"{script.name}: {name}() has no closing brace")
    return range(start, end + 1)


def check(script: Path) -> list[str]:
    lines = script.read_text(encoding="utf-8").splitlines()
    guard = _function_body(lines, "remove_path", script)

    errors = []
    for number, line in enumerate(lines):
        code = line.split("#", 1)[0].strip()
        if not DELETION.search(code) or number in guard or code in ALLOWED:
            continue
        errors.append(
            f"{script.name}:{number + 1}: deletion outside remove_path: {code}"
        )

    body = "\n".join(lines[guard.start : guard.stop])
    errors.extend(
        f"{script.name}: remove_path no longer refuses: {refusal}"
        for refusal in REFUSALS
        if refusal not in body
    )
    return errors


def main(argv: list[str]) -> int:
    script = Path(argv[1]) if len(argv) > 1 else REPO_ROOT / "uninstall.sh"
    errors = check(script)
    if errors:
        print("Deletion guard FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    print(
        f"Deletion guard passed — every rm/rmdir in {script.name} routes through remove_path."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
