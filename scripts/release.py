#!/usr/bin/env python3
"""Release orchestrator: run the steps in RELEASE.md as one guided CLI.

The release has a single natural fault line: ``git push origin <tag>`` triggers
PyPI publishing, which cannot be undone. Everything before it is local and
reversible; everything after is read-only verification. So this tool is two
subcommands with a review gate between them:

* ``prepare`` — bump the version, stamp CHANGELOG, commit. All local; nothing
  has left the machine. It stops and tells you to review the commit.
* ``publish`` — tag, push, watch the Release workflow, then verify. Asks for
  one explicit confirmation before the irreversible push.

The version transform itself is NOT reimplemented here: ``bump_version.py``
stays the sole owner of which files carry the version and how they are
rewritten (it is pure, offline, and separately tested). This orchestrator
shells out to it for the bump and imports it only for read-only lookups.

Verification (also runnable on its own via ``verify <tag>``) asserts the three
things RELEASE.md tells you to check by hand, so none of them can be forgotten:
the GitHub Release ships all five wheels, the published version installs from
PyPI, and the ``install.sh`` dry-run resolves the just-cut tag.
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
import time
from pathlib import Path

# bump_version is the version-transform engine; import it for pure reads and
# shell out to it for the mutating bump so it stays the single source of truth.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bump_version  # noqa: E402

REPO_ROOT = bump_version.REPO_ROOT
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
INSTALL_SH = REPO_ROOT / "install.sh"

# Filename stems of the five wheels every release must attach (order-agnostic).
EXPECTED_WHEEL_STEMS = (
    "pipefy-",
    "pipefy_mcp_server-",
    "pipefy_cli-",
    "pipefy_auth-",
    "pipefy_infra-",
)

# The [Unreleased] section spans from its heading to the next "## [" heading
# (or end of file). Group 1 is the heading line, group 2 the body between it
# and the next version heading.
UNRELEASED_RE = re.compile(
    r"^(## \[Unreleased\][^\n]*\n)(.*?)(?=^## \[|\Z)",
    re.MULTILINE | re.DOTALL,
)


class ReleaseError(RuntimeError):
    """A release step failed in a way the operator must resolve."""


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Echo and run a command in the repo root, raising on non-zero exit."""
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=REPO_ROOT, check=True, **kwargs)


def capture(cmd: list[str]) -> str:
    """Run a command in the repo root and return its stripped stdout."""
    result = subprocess.run(
        cmd, cwd=REPO_ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def pep440(version: str) -> str:
    """Normalize a raw version string to its PyPI/PEP 440 form.

    The git tag and ``__version__`` carry the SemVer-style string
    (``0.2.0-beta.1``); PyPI stores the normalized form (``0.2.0b1``). Installs
    must pin the latter, so verification derives it here rather than have the
    operator translate it by hand.
    """
    from packaging.version import Version

    return str(Version(version))


# --- preflight ------------------------------------------------------------


def current_branch() -> str:
    return capture(["git", "rev-parse", "--abbrev-ref", "HEAD"])


def working_tree_clean() -> bool:
    return capture(["git", "status", "--porcelain"]) == ""


def unreleased_body() -> str:
    """Return the text under ``## [Unreleased]``, or raise if the section is absent."""
    m = UNRELEASED_RE.search(CHANGELOG.read_text(encoding="utf-8"))
    if not m:
        raise ReleaseError(f"No '## [Unreleased]' section found in {CHANGELOG}")
    return m.group(2).strip()


def preflight_prepare() -> None:
    """Assert the repo is in a releasable state before mutating anything."""
    branch = current_branch()
    if branch != "main":
        raise ReleaseError(f"Must release from 'main', on '{branch}'")
    if not working_tree_clean():
        raise ReleaseError("Working tree is dirty; commit or stash first")

    run(["git", "fetch", "--quiet", "origin", "main"])
    local = capture(["git", "rev-parse", "HEAD"])
    remote = capture(["git", "rev-parse", "origin/main"])
    if local != remote:
        raise ReleaseError(
            "Local 'main' differs from 'origin/main'; pull/push so they match "
            "before cutting a release"
        )

    if not unreleased_body():
        raise ReleaseError(
            "'## [Unreleased]' in CHANGELOG.md is empty; add release notes first"
        )


# --- prepare ---------------------------------------------------------------


def stamp_changelog(version: str) -> None:
    """Rename ``## [Unreleased]`` to the dated version heading, re-seeding Unreleased.

    Follows Keep a Changelog: the accumulated notes become the released
    version's section, and a fresh empty ``## [Unreleased]`` is left on top for
    the next cycle (which ``preflight_prepare`` then requires to be non-empty).
    """
    today = datetime.date.today().isoformat()
    text = CHANGELOG.read_text(encoding="utf-8")
    new_heading = f"## [Unreleased]\n\n## [{version}] - {today}\n"
    new_text, count = UNRELEASED_RE.subn(rf"{new_heading}\2", text, count=1)
    if count != 1:
        raise ReleaseError(f"Expected one '## [Unreleased]' heading in {CHANGELOG}")
    CHANGELOG.write_text(new_text, encoding="utf-8")


def compute_target_version(bump_arg: str) -> tuple[str, str]:
    """Resolve ``(current, target)`` for a bump argument without mutating anything.

    Uses ``bump_version``'s own bump functions so the version previewed here is
    exactly what the bump will write. Lets ``prepare`` show the target and
    confirm it before touching any file — catching a wrong bump (e.g. expecting
    ``beta.1`` from ``prerelease``, which only increments the current track)
    while it is still a no-op to walk away.
    """
    current = bump_version.read_sdk_version()
    if bump_arg.lower().startswith("version="):
        return current, bump_version.parse_explicit_version(bump_arg)
    bumpers = {
        "major": bump_version.bump_major,
        "minor": bump_version.bump_minor,
        "patch": bump_version.bump_patch,
        "prerelease": bump_version.bump_prerelease,
    }
    if bump_arg not in bumpers:
        raise ReleaseError(
            f"Unknown bump {bump_arg!r}. Use major, minor, patch, prerelease, "
            "or version=X.Y.Z"
        )
    return current, bumpers[bump_arg](current)


def prepare(bump_arg: str, *, assume_yes: bool = False) -> str:
    """Bump, stamp the CHANGELOG, and commit. Returns the new version string."""
    preflight_prepare()

    current, target = compute_target_version(bump_arg)
    confirm(
        f"Will bump {current} -> {target} and cut tag v{target}. Proceed?",
        assume_yes=assume_yes,
    )

    # bump_version.py owns the transform; run its CLI so the file set and lock
    # refresh live in exactly one place.
    run(["uv", "run", "python", "scripts/bump_version.py", bump_arg])
    version = bump_version.read_sdk_version()
    if version != target:
        raise ReleaseError(
            f"bump_version wrote {version!r} but {target!r} was confirmed"
        )

    stamp_changelog(version)

    run(["git", "add", "-A"])
    run(["git", "commit", "-m", f"chore: release v{version}"])

    print()
    print(f"Prepared v{version}. Review the release commit:")
    print("    git show HEAD")
    print("Then publish with:")
    print("    uv run python scripts/release.py publish")
    return version


# --- publish ---------------------------------------------------------------


def confirm(prompt: str, *, assume_yes: bool) -> None:
    """Gate an irreversible step; require --yes when there is no interactive TTY."""
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise ReleaseError(f"{prompt} Re-run with --yes to proceed non-interactively.")
    if input(f"{prompt} [y/N] ").strip().lower() not in ("y", "yes"):
        raise ReleaseError("Aborted by operator")


def tag_exists(tag: str) -> bool:
    remote = capture(["git", "ls-remote", "--tags", "origin", tag])
    return bool(remote)


# A tag push does not create the workflow run synchronously — GitHub registers
# it a few seconds later — so the run lookup must poll rather than query once.
_RUN_APPEAR_TIMEOUT_S = 90
_RUN_POLL_INTERVAL_S = 3


def _find_release_run_id(tag: str) -> str:
    """Return the newest Release-workflow run id for ``tag``, or an empty string.

    The Release workflow runs only on ``v*`` tag pushes, so its runs carry the
    tag as ``headBranch``; filtering on ``headBranch == <tag>`` isolates this
    release's run from any other tag's, and ``gh`` lists newest first so a
    re-pushed tag resolves to its latest run.
    """
    runs = capture(
        [
            "gh",
            "run",
            "list",
            "--workflow",
            "Release",
            "--event",
            "push",
            "--limit",
            "20",
            "--json",
            "databaseId,headBranch",
            "--jq",
            f'.[] | select(.headBranch == "{tag}") | .databaseId',
        ]
    )
    lines = runs.splitlines()
    return lines[0] if lines else ""


def watch_release_workflow(tag: str) -> None:
    """Block until the Release workflow run for ``tag`` finishes, failing on failure.

    Polls for the run to appear (the push does not create it synchronously)
    before handing off to ``gh run watch``, which streams progress and exits
    non-zero if the run fails.
    """
    print(f"Waiting for the Release workflow run for {tag} to appear...")
    deadline = time.monotonic() + _RUN_APPEAR_TIMEOUT_S
    run_id = _find_release_run_id(tag)
    while not run_id and time.monotonic() < deadline:
        time.sleep(_RUN_POLL_INTERVAL_S)
        run_id = _find_release_run_id(tag)
    if not run_id:
        raise ReleaseError(
            f"No Release workflow run appeared for {tag} within "
            f"{_RUN_APPEAR_TIMEOUT_S}s. Check the Actions tab."
        )
    run(["gh", "run", "watch", run_id, "--exit-status"])


def publish(*, assume_yes: bool) -> None:
    """Tag, push, watch the workflow, then verify the published release."""
    if current_branch() != "main":
        raise ReleaseError("Must publish from 'main'")
    if not working_tree_clean():
        raise ReleaseError("Working tree is dirty; publish the exact reviewed commit")

    version = bump_version.read_sdk_version()
    tag = f"v{version}"
    if tag_exists(tag):
        raise ReleaseError(f"Tag {tag} already exists on origin")

    confirm(
        f"About to tag {tag}, push to origin, and publish to PyPI. "
        "This cannot be undone.",
        assume_yes=assume_yes,
    )

    run(["git", "tag", tag])
    run(["git", "push", "origin", "main"])
    run(["git", "push", "origin", tag])

    watch_release_workflow(tag)
    verify(tag)
    print(f"\nReleased {tag}.")
    print_release_links(tag, version)


# --- verify ----------------------------------------------------------------


def verify_github_wheels(tag: str) -> None:
    """Assert the GitHub Release for ``tag`` attaches exactly the five expected wheels."""
    names = capture(
        ["gh", "release", "view", tag, "--json", "assets", "--jq", ".assets[].name"]
    ).splitlines()
    wheels = [n for n in names if n.endswith(".whl")]
    missing = [
        stem
        for stem in EXPECTED_WHEEL_STEMS
        if not any(w.startswith(stem) for w in wheels)
    ]
    if missing:
        raise ReleaseError(
            f"Release {tag} is missing wheels for: {', '.join(missing)}. Got: {wheels}"
        )
    if len(wheels) != len(EXPECTED_WHEEL_STEMS):
        raise ReleaseError(
            f"Release {tag} has {len(wheels)} wheels, expected "
            f"{len(EXPECTED_WHEEL_STEMS)}: {wheels}"
        )
    print(f"GitHub Release {tag} ships all {len(wheels)} wheels.")


# PyPI (and its CDN) makes a freshly uploaded release installable only after a
# short propagation delay, so the install check must retry rather than fail on
# the first miss when run right after publish.
_PYPI_APPEAR_TIMEOUT_S = 120
_PYPI_POLL_INTERVAL_S = 10


def verify_pypi_install(version: str) -> None:
    """Assert the just-published CLI resolves and installs from PyPI.

    Retries while the release is still propagating; ``--refresh`` keeps uv from
    serving a cached "not found" from an earlier attempt.
    """
    spec = f"pipefy-cli=={pep440(version)}"
    print(f"Verifying PyPI install of {spec} ...")
    deadline = time.monotonic() + _PYPI_APPEAR_TIMEOUT_S
    while True:
        try:
            out = capture(["uvx", "--refresh", "--from", spec, "pipefy", "--version"])
            break
        except subprocess.CalledProcessError:
            if time.monotonic() >= deadline:
                raise ReleaseError(
                    f"{spec} did not become installable from PyPI within "
                    f"{_PYPI_APPEAR_TIMEOUT_S}s (still propagating, or the upload "
                    f"failed). Re-run `release.py verify v{version}` once it lands."
                ) from None
            print(f"  not on PyPI yet; retrying in {_PYPI_POLL_INTERVAL_S}s...")
            time.sleep(_PYPI_POLL_INTERVAL_S)
    if pep440(version) not in pep440_candidates(out):
        raise ReleaseError(
            f"`pipefy --version` from PyPI returned {out!r}, expected {version}"
        )
    print(f"PyPI install resolves: {out}")


def pep440_candidates(text: str) -> set[str]:
    """Normalized versions found in a ``--version`` output line."""
    from packaging.version import InvalidVersion, Version

    found: set[str] = set()
    for token in re.findall(r"\d[\w.\-+]*", text):
        try:
            found.add(str(Version(token)))
        except InvalidVersion:
            continue
    return found


def verify_installer_resolves(tag: str) -> None:
    """Assert install.sh's dry-run resolves the just-cut tag as the latest release."""
    print("Verifying install.sh resolves the latest release ...")
    result = subprocess.run(
        [
            "sh",
            str(INSTALL_SH),
            "--yes",
            "--no-skills",
            "--client",
            "none",
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    expected = f"Resolved tag: {tag}"
    if expected not in output:
        raise ReleaseError(
            f"install.sh dry-run did not report '{expected}'. Output:\n{output}"
        )
    print(f"install.sh resolves {tag}.")


def print_release_links(tag: str, version: str) -> None:
    """Print the GitHub Release and per-package PyPI links for a released tag.

    The repo comes from ``gh`` (so links point at whatever remote this checkout
    tracks, fork included) and the distribution names from the workspace member
    list, so a new published package appears here without editing a second list.
    """
    repo_url = capture(["gh", "repo", "view", "--json", "url", "--jq", ".url"])
    pep = pep440(version)
    print("\nLinks:")
    print(f"  GitHub Release: {repo_url}/releases/tag/{tag}")
    for dist in sorted(bump_version.workspace_members()):
        print(f"  PyPI {dist}: https://pypi.org/project/{dist}/{pep}/")


def version_from_tag(tag: str) -> str:
    """Strip a leading ``v`` from a git tag to get the PEP 440-ish version."""
    return tag[1:] if tag.startswith("v") else tag


def verify(tag: str) -> None:
    """Run all post-publish checks; raise on the first failure."""
    version = version_from_tag(tag)
    verify_github_wheels(tag)
    verify_pypi_install(version)
    verify_installer_resolves(tag)
    print(f"\nAll checks passed for {tag}.")


# --- entrypoint ------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_prepare = sub.add_parser(
        "prepare", help="bump version, stamp CHANGELOG, commit (all local)"
    )
    p_prepare.add_argument(
        "bump",
        help="major | minor | patch | prerelease | version=X.Y.Z",
    )
    p_prepare.add_argument(
        "--yes", action="store_true", help="skip the version confirmation prompt"
    )

    p_publish = sub.add_parser(
        "publish", help="tag, push, watch the workflow, then verify (irreversible)"
    )
    p_publish.add_argument(
        "--yes", action="store_true", help="skip the pre-push confirmation prompt"
    )

    p_verify = sub.add_parser("verify", help="re-run post-publish checks for a tag")
    p_verify.add_argument("tag", help="the release tag, e.g. v0.2.0-beta.1")

    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.bump, assume_yes=args.yes)
        elif args.command == "publish":
            publish(assume_yes=args.yes)
        elif args.command == "verify":
            verify(args.tag)
            print_release_links(args.tag, version_from_tag(args.tag))
    except (ReleaseError, subprocess.CalledProcessError) as exc:
        print(f"\nrelease: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
