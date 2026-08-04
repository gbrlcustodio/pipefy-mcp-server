#!/usr/bin/env python3
"""Guard the packaging smoke install: check the wheels, then launch every command.

Two modes, both keyed off one list of published members
(``PUBLISHED_DISTRIBUTIONS``):

``--check-wheels <directory>``
    Run with any interpreter, **before** the install. Asserts the directory holds
    exactly one wheel per published member. An incomplete set must not reach
    ``pip``: the sibling ``==`` pins let pip resolve the absent member from the
    index, so the smoke would pass against an artifact this build never produced.

no arguments
    Run with the **smoke virtualenv's** interpreter, after the install::

        .venv-smoke/bin/python scripts/smoke_entry_points.py

    Launches every console entry point. It reads installed distribution metadata
    rather than the checkout's ``pyproject.toml`` files, so it reports what an
    install actually exposes: a wheel that ships without its entry point, or a
    member missing from the install, fails here.

Three workflows share this script -- ``ci.yml``, ``release.yml``, and
``packaging-smoke.yml`` -- so "every published entry point" has one definition
instead of a launch list copied into each job, where a newly added script would
have to be remembered three times.
"""

from __future__ import annotations

import re
import subprocess
import sys
import sysconfig
from collections.abc import Callable, Iterable, Mapping, Sequence
from importlib.metadata import Distribution, distributions
from pathlib import Path

# The workspace members published to PyPI. Explicit rather than discovered so
# that adding a member forces a decision here; release.yml guards the same list
# from the wheel side (it fails unless dist/ holds exactly one wheel per member).
PUBLISHED_DISTRIBUTIONS = frozenset(
    {"pipefy", "pipefy-auth", "pipefy-cli", "pipefy-infra", "pipefy-mcp-server"}
)

# Every discovered script is launched, so a newly added entry point is covered
# without touching this file. This floor is what catches a *lost* one, which
# discovery alone would read as success.
REQUIRED_SCRIPTS = frozenset({"pipefy", "pipefy-mcp-server"})

LAUNCH_TIMEOUT_SECONDS = 120

USAGE = "usage: smoke_entry_points.py [--check-wheels <directory>]"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class SmokeError(RuntimeError):
    """A fresh install is missing a package or a script, or fails to launch one."""


def canonical_name(raw: str) -> str:
    """Normalize to PEP 503 form, so ``pipefy_cli`` and ``pipefy-cli`` compare equal."""
    return re.sub(r"[-_.]+", "-", raw).lower()


def index_published(dists: Iterable[Distribution]) -> dict[str, Distribution]:
    """Map canonical name to distribution, keeping only published workspace members."""
    found: dict[str, Distribution] = {}
    for dist in dists:
        name = canonical_name(dist.name)
        if name in PUBLISHED_DISTRIBUTIONS:
            found.setdefault(name, dist)
    return found


def resolve_scripts(found: Mapping[str, Distribution]) -> list[str]:
    """Return the console scripts the installed members declare, or raise."""
    missing = sorted(PUBLISHED_DISTRIBUTIONS - set(found))
    if missing:
        raise SmokeError(
            f"missing from the install: {', '.join(missing)}. "
            "A fresh install must carry every published workspace member."
        )
    scripts = {
        entry_point.name
        for dist in found.values()
        for entry_point in dist.entry_points
        if entry_point.group == "console_scripts"
    }
    absent = sorted(REQUIRED_SCRIPTS - scripts)
    if absent:
        raise SmokeError(
            f"installed, but no console script named {', '.join(absent)}: "
            "a wheel stopped shipping its entry point."
        )
    return sorted(scripts)


def wheel_distribution(filename: str) -> str:
    """Read the distribution name out of a wheel filename (PEP 427 name-version-...)."""
    return canonical_name(filename.split("-")[0])


def check_wheels(directory: str | Path) -> list[str]:
    """Assert the directory holds exactly one wheel per published member.

    Installing an incomplete set is not a hard error for pip: it satisfies the
    absent member from the index through the sibling ``==`` pins, and the smoke
    then passes against a wheel this build never produced. So the membership
    check has to happen before the install, not after it.
    """
    wheels = sorted(path.name for path in Path(directory).glob("*.whl"))
    by_distribution: dict[str, list[str]] = {}
    for name in wheels:
        by_distribution.setdefault(wheel_distribution(name), []).append(name)

    missing = sorted(PUBLISHED_DISTRIBUTIONS - set(by_distribution))
    if missing:
        raise SmokeError(
            f"{directory} has no wheel for: {', '.join(missing)}. "
            "pip would resolve that member from the index instead, so the smoke "
            "would test an artifact this build did not produce."
        )
    unexpected = sorted(set(by_distribution) - PUBLISHED_DISTRIBUTIONS)
    if unexpected:
        raise SmokeError(
            f"{directory} holds an unexpected wheel for: {', '.join(unexpected)}. "
            "Add the member to PUBLISHED_DISTRIBUTIONS, or remove the wheel."
        )
    duplicated = sorted(
        name for name, built in by_distribution.items() if len(built) > 1
    )
    if duplicated:
        raise SmokeError(
            f"{directory} holds more than one wheel for: {', '.join(duplicated)}. "
            "A wheel left over from an earlier version makes the install ambiguous."
        )
    return wheels


def launch(
    scripts: Sequence[str],
    script_dir: str | Path,
    runner: Runner | None = None,
) -> None:
    """Run ``<script> --help`` for each script, raising on the first failure."""
    # Resolved here rather than as a default argument, which would bind
    # subprocess.run once at import and ignore any later substitution.
    runner = runner if runner is not None else subprocess.run
    for script in scripts:
        path = Path(script_dir) / script
        if not path.exists():
            raise SmokeError(
                f"{script} is declared in the installed metadata, but {path} does not exist."
            )
        try:
            completed = runner(
                [str(path), "--help"],
                capture_output=True,
                text=True,
                timeout=LAUNCH_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise SmokeError(
                f"{script} --help did not return within {LAUNCH_TIMEOUT_SECONDS}s."
            ) from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise SmokeError(
                f"{script} --help exited {completed.returncode}.\n{detail}"
            )
        print(f"  {script} --help -> ok")


def main(argv: Sequence[str] | None = None) -> int:
    # sys.argv is read at the entry point below, never here: a default that
    # reached for it would pick up the arguments of whatever runs this module.
    args = [] if argv is None else list(argv)
    try:
        if args[:1] == ["--check-wheels"]:
            if len(args) != 2:
                raise SmokeError(USAGE)
            directory = args[1]
            wheels = check_wheels(directory)
            print(f"{directory} holds one wheel per published member:")
            for name in wheels:
                print(f"  {name}")
            return 0
        if args:
            raise SmokeError(USAGE)
        script_dir = sysconfig.get_path("scripts")
        scripts = resolve_scripts(index_published(distributions()))
        print(f"Launching {len(scripts)} console entry point(s) from {script_dir}")
        launch(scripts, script_dir)
    except SmokeError as exc:
        print(f"packaging smoke failed: {exc}", file=sys.stderr)
        return 1
    print("Every published console entry point launched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
