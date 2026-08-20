#!/usr/bin/env python3
"""A consumer fed by one of this script's own functions has to read to the end.

``client_rows``, ``all_client_rows`` and ``records`` emit a line at a time. A
consumer that stops early — ``break`` out of a ``while read``, ``exit`` from an
awk rule, ``head``, ``grep -q`` — closes the read end while the producer is
still writing, and the producer's next write gets EPIPE. dash reports that as
``printf: I/O error`` on stderr, from a scan that is supposed to write nothing
there.

It cannot be caught by running the thing. Whether the producer is still writing
when the consumer leaves depends on how much fits in the pipe buffer, so the
same code reproduces on one platform and not another, which is how the last one
survived a fix for its siblings. This asserts the shape instead: no early exit
in a pipeline whose producer is a function defined in the file.

An ``exit`` inside an awk ``END`` block is not an early exit — END runs after
the input is consumed — so those are allowed and are how these consumers say
"found it" without leaving early.

Usage: check_pipe_drain.py [path/to/uninstall.sh ...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

DEFINITION = re.compile(r"^([a-z_][a-z0-9_]*)\(\) \{")
# A pipeline that starts with a bare call: at the start of a line, or opening a
# command substitution. Anything else (a `printf` of a variable, an external
# command) is not one of the streaming producers this is about.
CALL = re.compile(r"(?:^|\$\()\s*([a-z_][a-z0-9_]*)(?:\s+[^|]*?)?\s\|\s*(.+)$")
END_BLOCK = re.compile(r"\bEND\s*\{[^}]*\}", re.S)

EARLY = (
    (re.compile(r"\bexit\b"), "awk leaves on its first match"),
    (re.compile(r"\bhead\b"), "head closes the pipe after N lines"),
    (re.compile(r"grep\s+(-\w*[qm]|-\w+\s+-\w*[qm])"), "grep stops at the first match"),
)


def _logical_lines(text: str) -> list[tuple[int, str]]:
    """Backslash continuations joined, so a wrapped pipeline reads as one."""
    out: list[tuple[int, str]] = []
    buffer = ""
    start = 1
    for number, line in enumerate(text.splitlines(), start=1):
        if not buffer:
            start = number
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            buffer += stripped[:-1] + " "
            continue
        out.append((start, buffer + stripped))
        buffer = ""
    if buffer:
        out.append((start, buffer))
    return out


def _loop_body(lines: list[tuple[int, str]], index: int) -> str:
    """From a `| while ... do` to its `done`, so a `break` inside is visible."""
    depth = 0
    body = []
    for _, line in lines[index:]:
        body.append(line)
        depth += len(re.findall(r"(?:^|\s|;)do\b", line))
        depth -= len(re.findall(r"(?:^|\s|;)done\b", line))
        if depth <= 0 and len(body) > 1:
            break
    return "\n".join(body)


def check(script: Path) -> list[str]:
    text = script.read_text(encoding="utf-8")
    functions = {
        match.group(1)
        for match in (DEFINITION.match(line) for line in text.splitlines())
        if match
    }
    lines = _logical_lines(text)

    errors = []
    for index, (number, line) in enumerate(lines):
        code = line.split("#", 1)[0] if not line.lstrip().startswith("#") else ""
        match = CALL.search(code)
        if match is None or match.group(1) not in functions:
            continue
        producer, rest = match.group(1), match.group(2)
        where = f"{script.name}:{number}"
        if re.match(r"while\b", rest):
            body = _loop_body(lines, index)
            if re.search(r"(?:^|\s|;)break\b", body):
                errors.append(
                    f"{where}: `break` leaves the loop while {producer} is still "
                    f"writing; read to the end and keep the first match instead"
                )
            continue
        for pattern, why in EARLY:
            if pattern.search(END_BLOCK.sub("", rest)):
                errors.append(f"{where}: {why}, and {producer} is still writing")
                break
    return errors


def main(argv: list[str]) -> int:
    scripts = [Path(a) for a in argv[1:]] or [REPO_ROOT / "uninstall.sh"]
    errors = [error for script in scripts for error in check(script)]
    if errors:
        print("Pipe drain check FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    print(
        "Pipe drain check passed — every consumer of a local producer reads to the end."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
