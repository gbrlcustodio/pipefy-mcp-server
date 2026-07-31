#!/usr/bin/env python3
"""Release orchestrator: run the steps in RELEASE.md as one guided CLI.

The release has a single natural fault line: ``git push origin <tag>`` triggers
PyPI publishing, which cannot be undone. Everything before it is local and
reversible; everything after is read-only verification. So this tool splits
into subcommands with a review gate between the reversible and irreversible
halves:

* ``release-pr`` — branch off the latest ``origin/dev``, run the ``prepare``
  bump, push, and open a release PR into ``main``. Reversible; the PR review
  is the gate.
* ``prepare`` — bump the version, stamp CHANGELOG, commit on ``main``. All
  local; nothing has left the machine. It stops and tells you to review.
* ``publish`` — tag, push, watch the Release workflow, then verify. Asks for
  one explicit confirmation before the irreversible push.
* ``alpha`` — cut a staging alpha off ``dev`` in one step (bump, tag, publish).
* ``verify`` — re-run the post-publish checks for a tag.

Which branch a tag may be cut from follows from the version itself, not the
operator's checkout (``release_branch_for``): **alphas ship from ``dev``** as
staging cuts, **betas and stables ship from ``main``**. The two flows differ in
more than the branch — an alpha does not stamp the CHANGELOG, so consecutive
alphas share one accumulating ``## [Unreleased]`` section that the eventual beta
promotion stamps in full — so they are separate subcommands rather than one with
a flag.

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

DEV_BRANCH = "dev"
MAIN_BRANCH = "main"

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


def release_branch_for(version: str) -> str:
    """The branch ``version`` must be cut from, derived from its pre-release track.

    Alphas are staging cuts off ``dev``: they exist so a release can be exercised
    in staging (the hosted MCP server wrapper pins an exact PyPI version) before
    it ships. Betas and stables ship from ``main``. Deriving the branch from the
    version's own track — rather than trusting the operator's checkout — means a
    tag can never be cut from the wrong branch.
    """
    track = bump_version.prerelease_track(version)
    return DEV_BRANCH if track == "alpha" else MAIN_BRANCH


def _refuse_alpha_target(target: str) -> None:
    """Refuse an alpha target in a ``main``-bound flow (``prepare``, ``release_pr``).

    Only ``alpha`` may cut an alpha, because it is the one flow that skips the
    CHANGELOG stamp. Reaching an alpha through a ``main``-bound flow would burn
    the accumulating ``## [Unreleased]`` section into an alpha heading and aim
    that commit at ``main``. ``publish`` refuses the tag later so nothing reaches
    PyPI, but by then the CHANGELOG contract is already broken, and a merged
    release PR would carry the damage onto ``main``.
    """
    if release_branch_for(target) != MAIN_BRANCH:
        raise ReleaseError(
            f"v{target} is an alpha, a staging cut off {DEV_BRANCH}. Cut it with "
            f"'release.py alpha <bump>', or promote the line to a "
            f"{MAIN_BRANCH}-bound release with the 'beta' bump."
        )


def preflight_prepare(branch: str) -> None:
    """Assert the repo is in a releasable state before mutating anything."""
    checked_out = current_branch()
    if checked_out != branch:
        raise ReleaseError(f"Must release from {branch!r}, on {checked_out!r}")
    if not working_tree_clean():
        raise ReleaseError("Working tree is dirty; commit or stash first")

    run(["git", "fetch", "--quiet", "origin", branch])
    local = capture(["git", "rev-parse", "HEAD"])
    remote = capture(["git", "rev-parse", f"origin/{branch}"])
    if local != remote:
        raise ReleaseError(
            f"Local {branch!r} differs from 'origin/{branch}'; pull/push so they "
            "match before cutting a release"
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


def target_for(bump_arg: str, current: str) -> str:
    """Apply a bump argument to ``current`` via ``bump_version``'s own functions.

    Uses bump_version's bump logic so the version previewed here is exactly what
    the bump will write — letting a caller show the target and confirm it before
    touching any file, and catching a wrong bump (e.g. expecting ``beta.1`` from
    ``prerelease``, which only increments the current track) while walking away
    is still a no-op.
    """
    if bump_arg.lower().startswith("version="):
        return bump_version.parse_explicit_version(bump_arg)
    bumpers = {
        "major": bump_version.bump_major,
        "minor": bump_version.bump_minor,
        "patch": bump_version.bump_patch,
        "prerelease": bump_version.bump_prerelease,
        "beta": bump_version.bump_beta,
    }
    if bump_arg not in bumpers:
        raise ReleaseError(
            f"Unknown bump {bump_arg!r}. Use major, minor, patch, prerelease, "
            "beta, or version=X.Y.Z"
        )
    return bumpers[bump_arg](current)


def compute_target_version(bump_arg: str) -> tuple[str, str]:
    """Resolve ``(current, target)`` from the working tree's current version."""
    current = bump_version.read_sdk_version()
    return current, target_for(bump_arg, current)


def _apply_prepare(bump_arg: str, target: str, *, stamp: bool = True) -> str:
    """Bump, optionally stamp the CHANGELOG, and commit on the current branch.

    The mutating core shared by ``prepare`` (main flow), ``release_pr``
    (dev→main flow), and ``alpha`` (staging cut off dev); callers own the
    preflight and confirmation. Returns the version bump_version actually wrote.

    ``stamp=False`` leaves ``## [Unreleased]`` intact — what the alpha flow
    needs, since consecutive alphas share one accumulating section (see
    ``alpha``).
    """
    # bump_version.py owns the transform; run its CLI so the file set and lock
    # refresh live in exactly one place.
    run(["uv", "run", "python", "scripts/bump_version.py", bump_arg])
    version = bump_version.read_sdk_version()
    if version != target:
        raise ReleaseError(
            f"bump_version wrote {version!r} but {target!r} was confirmed"
        )
    if stamp:
        stamp_changelog(version)
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", f"chore: release v{version}"])
    return version


def prepare(bump_arg: str, *, assume_yes: bool = False) -> str:
    """Bump, stamp the CHANGELOG, and commit on ``main``. Returns the version."""
    preflight_prepare(MAIN_BRANCH)

    current, target = compute_target_version(bump_arg)
    _refuse_alpha_target(target)
    confirm(
        f"Will bump {current} -> {target} and cut tag v{target}. Proceed?",
        assume_yes=assume_yes,
    )
    version = _apply_prepare(bump_arg, target)

    print()
    print(f"Prepared v{version}. Review the release commit:")
    print("    git show HEAD")
    print("Then publish with:")
    print("    uv run python scripts/release.py publish")
    return version


# --- release-pr (dev -> main) ----------------------------------------------


def branch_exists(branch: str) -> bool:
    """Whether ``branch`` exists locally or on origin."""
    local = capture(["git", "branch", "--list", branch])
    remote = capture(["git", "ls-remote", "--heads", "origin", branch])
    return bool(local or remote)


def _show_at(ref: str, path: str) -> str:
    """Return the contents of ``path`` as of ``ref`` without checking it out."""
    return capture(["git", "show", f"{ref}:{path}"])


def _version_at(ref: str) -> str:
    """The lockstep version at ``ref`` (read from its root pyproject).

    ``release_pr`` derives the target from ``origin/dev``'s version, not the
    working tree's — the branch it is invoked from may carry a different one —
    and compares against ``origin/main`` to refuse a downgrade.
    """
    import tomllib

    data = tomllib.loads(_show_at(ref, "pyproject.toml"))
    return data["project"]["version"]


def _target_ahead_of_main(target: str, main_version: str) -> bool:
    """Whether ``target`` is a strictly newer version than ``main_version``."""
    from packaging.version import Version

    return Version(target) > Version(main_version)


def _dev_unreleased_body() -> str:
    """The text under ``## [Unreleased]`` in ``origin/dev``'s CHANGELOG."""
    m = UNRELEASED_RE.search(_show_at(f"origin/{DEV_BRANCH}", "CHANGELOG.md"))
    if not m:
        raise ReleaseError(
            f"No '## [Unreleased]' section in CHANGELOG.md on origin/{DEV_BRANCH}"
        )
    return m.group(2).strip()


def _release_pr_body(previous: str, version: str, released: str) -> str:
    """Body for the dev→main release PR.

    Inlines the released content (the ``[Unreleased]`` notes being finalized)
    so a reviewer sees what ships without opening the CHANGELOG diff.
    """
    from packaging.version import Version

    today = datetime.date.today().isoformat()
    kind = "pre-release" if Version(version).is_prerelease else "stable"
    return (
        f"Cuts `v{version}`, capturing everything merged into `{DEV_BRANCH}` "
        f"since `v{previous}`. Tagging publishes a GitHub Release with wheels "
        f"and a {kind} PyPI upload.\n\n"
        "## What this PR contains\n\n"
        f"- Lockstep version bump `{previous}` -> `{version}` across every "
        "workspace package's `__init__.py`, the root `pyproject.toml`, "
        "`.claude-plugin/plugin.json`, and `uv.lock`.\n"
        f"- `CHANGELOG.md`: `## [Unreleased]` finalized to "
        f"`## [{version}] - {today}`; the Release workflow uses this section as "
        "the GitHub Release body.\n\n"
        "## Released content (already in dev)\n\n"
        f"{released}\n\n"
        "## After merge\n\n"
        f"Run `uv run python scripts/release.py publish` from `{MAIN_BRANCH}` "
        "to tag and publish — the one irreversible, human-gated step."
    )


def release_pr(bump_arg: str, *, assume_yes: bool = False) -> None:
    """Cut a release-prep branch off the latest ``dev`` and open a PR into ``main``.

    Automates the reversible half of a dev→main release: fetch dev, branch off
    it, bump + stamp + commit, push, and open the PR. Deliberately does NOT
    tag or publish — that stays a human ``publish`` from ``main`` after review,
    so the tag push still triggers the Release workflow.
    """
    if not working_tree_clean():
        raise ReleaseError("Working tree is dirty; commit or stash first")

    run(["git", "fetch", "--quiet", "origin", DEV_BRANCH, MAIN_BRANCH])

    released = _dev_unreleased_body()
    if not released:
        raise ReleaseError(
            f"'## [Unreleased]' in CHANGELOG.md on origin/{DEV_BRANCH} is empty; "
            "add release notes first"
        )

    current = _version_at(f"origin/{DEV_BRANCH}")
    target = target_for(bump_arg, current)

    # Refuse before the branch/bump: on an alpha line, `prerelease` computes the
    # next alpha, which belongs to the `alpha` flow (no CHANGELOG stamp), not to
    # a main-bound release PR.
    _refuse_alpha_target(target)

    # Guard against a downgrade-shaped release: if origin/dev is behind
    # origin/main (a release bump on main not back-merged into dev), the bump
    # computed from dev can land below main's already-released version.
    main_version = _version_at(f"origin/{MAIN_BRANCH}")
    if not _target_ahead_of_main(target, main_version):
        raise ReleaseError(
            f"Computed target v{target} is not ahead of origin/{MAIN_BRANCH} "
            f"(v{main_version}); origin/{DEV_BRANCH} (v{current}) is behind "
            f"{MAIN_BRANCH}. Back-merge {MAIN_BRANCH} into {DEV_BRANCH} before "
            "cutting a release."
        )

    branch = f"rc-{MAIN_BRANCH}/release/v{target}"
    if branch_exists(branch):
        raise ReleaseError(f"Branch {branch} already exists")

    confirm(
        f"Will branch off origin/{DEV_BRANCH}, bump {current} -> {target} "
        f"(origin/{MAIN_BRANCH} is at {main_version}), and open a release PR "
        f"into {MAIN_BRANCH}. Proceed?",
        assume_yes=assume_yes,
    )

    run(["git", "checkout", "-b", branch, f"origin/{DEV_BRANCH}"])
    version = _apply_prepare(bump_arg, target)
    run(["git", "push", "-u", "origin", branch])

    url = capture(
        [
            "gh",
            "pr",
            "create",
            "--base",
            MAIN_BRANCH,
            "--head",
            branch,
            "--title",
            f"chore: release v{version}",
            "--body",
            _release_pr_body(current, version, released),
        ]
    )
    print(f"\nOpened release PR: {url}")
    print(
        f"After it is approved and merged into {MAIN_BRANCH}, run from {MAIN_BRANCH}:"
    )
    print(f"    git checkout {MAIN_BRANCH} && git pull")
    print("    uv run python scripts/release.py publish")


# --- alpha (staging cut off dev) -------------------------------------------


def alpha(bump_arg: str, *, assume_yes: bool = False) -> None:
    """Cut a staging alpha straight off ``dev``: bump, commit, tag, push, verify.

    Alphas exist to exercise a release in staging before it ships, so there is no
    release PR — ``dev`` is already the integration branch and the tag is cut on
    it in place. The wheels land on PyPI as a pre-release for the hosted MCP
    server wrapper to pin.

    The CHANGELOG is deliberately NOT stamped. ``## [Unreleased]`` keeps
    accumulating across ``alpha.1..alpha.N`` and is what the Release workflow
    uses as an alpha's release body, so the eventual ``beta`` promotion on
    ``main`` still stamps the whole set into one section rather than finding the
    notes already spent.
    """
    preflight_prepare(DEV_BRANCH)

    run(["git", "fetch", "--quiet", "origin", MAIN_BRANCH])
    current, target = compute_target_version(bump_arg)

    if release_branch_for(target) != DEV_BRANCH:
        raise ReleaseError(
            f"v{target} is not an alpha, so it does not belong on {DEV_BRANCH}. "
            f"Ship it from {MAIN_BRANCH} with 'release-pr' + 'publish'."
        )

    # An alpha's release body is dev's ## [Unreleased]. If dev is behind main,
    # that section still holds notes main has already released under its own
    # heading, so the alpha would re-ship them — and PEP 440 would order the
    # alpha below main's beta besides.
    main_version = _version_at(f"origin/{MAIN_BRANCH}")
    if not _target_ahead_of_main(target, main_version):
        raise ReleaseError(
            f"Computed target v{target} is not ahead of origin/{MAIN_BRANCH} "
            f"(v{main_version}); origin/{DEV_BRANCH} (v{current}) is behind "
            f"{MAIN_BRANCH}. Back-merge {MAIN_BRANCH} into {DEV_BRANCH} before "
            "cutting an alpha."
        )

    confirm(
        f"Will bump {current} -> {target} on {DEV_BRANCH} and cut tag v{target} "
        f"(origin/{MAIN_BRANCH} is at {main_version}). Proceed?",
        assume_yes=assume_yes,
    )

    version = _apply_prepare(bump_arg, target, stamp=False)
    _tag_and_publish(DEV_BRANCH, version, assume_yes=assume_yes)
    print(
        f"\nStaging alpha v{version} is on PyPI. Pin it in the hosted server "
        "wrapper to exercise this release in staging."
    )
    print(f"When it checks out, promote it to a beta release from {MAIN_BRANCH}:")
    print("    uv run python scripts/release.py release-pr beta")


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
    """Whether ``tag`` already exists on origin."""
    return bool(capture(["git", "ls-remote", "--tags", "origin", tag]))


def local_tag_exists(tag: str) -> bool:
    """Whether ``tag`` already exists in the local repository."""
    return bool(capture(["git", "tag", "--list", tag]))


# A tag push does not create the workflow run synchronously — GitHub registers
# it a few seconds later — so the run lookup must poll rather than query once.
_RUN_APPEAR_TIMEOUT_S = 90
_RUN_POLL_INTERVAL_S = 3


def _release_run_ids(tag: str) -> list[str]:
    """Release-workflow run ids for ``tag``, newest first.

    The Release workflow runs only on ``v*`` tag pushes, so its runs carry the
    tag as ``headBranch``; filtering on ``headBranch == <tag>`` isolates this
    tag's runs from any other tag's.
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
    return runs.splitlines()


def _newest_run_id(tag: str, exclude: frozenset[str]) -> str:
    """Newest Release run id for ``tag`` not in ``exclude``, or an empty string."""
    for run_id in _release_run_ids(tag):  # newest first
        if run_id not in exclude:
            return run_id
    return ""


def watch_release_workflow(tag: str, *, exclude: frozenset[str] = frozenset()) -> None:
    """Block until the Release workflow run for ``tag`` finishes, failing on failure.

    Polls for a run not in ``exclude`` — the runs that already existed before
    this push — so a re-cut of the same tag waits for its genuinely new run
    rather than attaching to a prior completed one. Hands off to
    ``gh run watch``, which streams progress and exits non-zero on failure.
    """
    print(f"Waiting for the Release workflow run for {tag} to appear...")
    deadline = time.monotonic() + _RUN_APPEAR_TIMEOUT_S
    run_id = _newest_run_id(tag, exclude)
    while not run_id and time.monotonic() < deadline:
        time.sleep(_RUN_POLL_INTERVAL_S)
        run_id = _newest_run_id(tag, exclude)
    if not run_id:
        raise ReleaseError(
            f"No new Release workflow run appeared for {tag} within "
            f"{_RUN_APPEAR_TIMEOUT_S}s. Check the Actions tab."
        )
    run(["gh", "run", "watch", run_id, "--exit-status"])


def _tag_and_publish(branch: str, version: str, *, assume_yes: bool) -> None:
    """Tag ``version``, push ``branch`` and the tag, watch the workflow, verify.

    The irreversible half, shared by ``publish`` (beta/stable off ``main``) and
    ``alpha`` (staging cut off ``dev``) so both cross the same gate and run the
    same post-publish checks.
    """
    # Re-assert the branch here, not just in the caller's preflight: the bump
    # commit lands in between, and the tag is cut from whatever HEAD is now. The
    # Release workflow checks this again server-side, since that is where the
    # publish actually happens.
    checked_out = current_branch()
    if checked_out != branch:
        raise ReleaseError(
            f"v{version} must be tagged on {branch!r}, but {checked_out!r} is "
            "checked out"
        )
    if release_branch_for(version) != branch:
        raise ReleaseError(
            f"v{version} does not belong on {branch!r} "
            f"(its track ships from {release_branch_for(version)!r})"
        )

    tag = f"v{version}"
    if tag_exists(tag):
        raise ReleaseError(f"Tag {tag} already exists on origin")
    if local_tag_exists(tag):
        raise ReleaseError(
            f"Tag {tag} exists locally (likely from an earlier interrupted "
            f"publish) but not on origin. Delete it with 'git tag -d {tag}' "
            "and re-run."
        )

    confirm(
        f"About to tag {tag}, push to origin, and publish to PyPI. "
        "This cannot be undone.",
        assume_yes=assume_yes,
    )

    # Push the branch before tagging so a rejected branch push never leaves a
    # dangling local tag to trip the next attempt.
    run(["git", "push", "origin", branch])
    run(["git", "tag", tag])
    # Snapshot runs that already exist for this tag (from a prior cut) so the
    # watcher waits for the run this push creates, not a stale completed one.
    prior_runs = frozenset(_release_run_ids(tag))
    run(["git", "push", "origin", tag])

    watch_release_workflow(tag, exclude=prior_runs)
    verify(tag)
    print(f"\nReleased {tag}.")
    print_release_links(tag, version)


def publish(*, assume_yes: bool) -> None:
    """Tag, push, watch the workflow, then verify the published release."""
    version = bump_version.read_sdk_version()
    if release_branch_for(version) != MAIN_BRANCH:
        raise ReleaseError(
            f"v{version} is an alpha, which is a staging cut off {DEV_BRANCH}. "
            f"Use 'release.py alpha <bump>' instead, or promote it to a beta "
            f"first with 'release-pr beta'."
        )
    if current_branch() != MAIN_BRANCH:
        raise ReleaseError(f"Must publish from {MAIN_BRANCH!r}")
    if not working_tree_clean():
        raise ReleaseError("Working tree is dirty; publish the exact reviewed commit")

    _tag_and_publish(MAIN_BRANCH, version, assume_yes=assume_yes)


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


def _installer_dry_run() -> str:
    """Run install.sh's dry-run and return its combined output."""
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
    return result.stdout + result.stderr


def verify_installer_resolves(tag: str) -> None:
    """Assert install.sh's dry-run resolves the just-cut tag as the latest release."""
    print("Verifying install.sh resolves the latest release ...")
    output = _installer_dry_run()
    expected = f"Resolved tag: {tag}"
    if expected not in output:
        raise ReleaseError(
            f"install.sh dry-run did not report '{expected}'. Output:\n{output}"
        )
    print(f"install.sh resolves {tag}.")


def verify_installer_skips(tag: str) -> None:
    """Assert install.sh's dry-run resolves a non-alpha release, not ``tag``.

    The inverse of ``verify_installer_resolves``, and the check that keeps a
    staging alpha from leaking into the public one-line install: the alpha is on
    PyPI (so the hosted wrapper can pin it) and has a GitHub Release (so its
    wheels are downloadable), but ``install.sh`` must stay on the newest
    non-alpha release. Without this, publishing an alpha would silently
    repoint ``curl … | sh`` at an untested build.

    Asserts the resolved tag is not an alpha at all, rather than merely not this
    one: a filter that skipped only the newest alpha would still leave the
    installer on an older staging cut, which is the same leak.
    """
    print(f"Verifying install.sh skips the staging alpha {tag} ...")
    output = _installer_dry_run()
    if f"Resolved tag: {tag}" in output:
        raise ReleaseError(
            f"install.sh dry-run resolved the staging alpha {tag}; it must stay "
            f"on the newest non-alpha release. Output:\n{output}"
        )
    m = re.search(r"Resolved tag: (\S+)", output)
    if not m:
        raise ReleaseError(
            f"install.sh dry-run reported no resolved tag at all. Output:\n{output}"
        )
    resolved = m.group(1)
    from packaging.version import InvalidVersion

    try:
        track = bump_version.prerelease_track(version_from_tag(resolved))
    except InvalidVersion:
        raise ReleaseError(
            f"install.sh resolved {resolved!r}, which is not a version tag; "
            f"cannot confirm it is not an alpha. Output:\n{output}"
        ) from None
    if track == "alpha":
        raise ReleaseError(
            f"install.sh resolved {resolved}, which is also an alpha; the "
            f"installer must land on a non-alpha release. Output:\n{output}"
        )
    print(f"install.sh stays on {resolved}.")


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
    """Run all post-publish checks; raise on the first failure.

    The installer check flips by track: a beta/stable must become what
    ``install.sh`` hands out, an alpha must not.
    """
    version = version_from_tag(tag)
    verify_github_wheels(tag)
    verify_pypi_install(version)
    if bump_version.prerelease_track(version) == "alpha":
        verify_installer_skips(tag)
    else:
        verify_installer_resolves(tag)
    print(f"\nAll checks passed for {tag}.")


# --- entrypoint ------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_prepare = sub.add_parser(
        "prepare", help="bump version, stamp CHANGELOG, commit on main (all local)"
    )
    p_prepare.add_argument(
        "bump",
        help="major | minor | patch | prerelease | beta | version=X.Y.Z",
    )
    p_prepare.add_argument(
        "--yes", action="store_true", help="skip the version confirmation prompt"
    )

    p_release_pr = sub.add_parser(
        "release-pr", help="branch off dev, prepare, open a release PR into main"
    )
    p_release_pr.add_argument(
        "bump",
        help="major | minor | patch | prerelease | beta | version=X.Y.Z",
    )
    p_release_pr.add_argument(
        "--yes", action="store_true", help="skip the confirmation prompt"
    )

    p_alpha = sub.add_parser(
        "alpha", help="cut a staging alpha off dev: bump, tag, publish (irreversible)"
    )
    p_alpha.add_argument(
        "bump",
        help="prerelease (next alpha in the line) | version=X.Y.Z-alpha.N",
    )
    p_alpha.add_argument(
        "--yes", action="store_true", help="skip the confirmation prompts"
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
        elif args.command == "release-pr":
            release_pr(args.bump, assume_yes=args.yes)
        elif args.command == "alpha":
            alpha(args.bump, assume_yes=args.yes)
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
