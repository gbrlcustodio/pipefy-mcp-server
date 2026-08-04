#!/usr/bin/env python3
"""Open the ``main`` -> ``dev`` back-merge pull request, or record why one could not be.

Anything merged directly into ``main`` -- a hotfix, a docs fix, a LICENSE --
leaves ``dev`` behind until a human remembers to back-merge. Nothing on the
GitHub side notices, so the drift is silent from the moment it happens until
the next release cut trips over it, which can be days later and is diagnosed by
whoever happens to be cutting rather than by whoever caused it.

``release.py release-pr`` already refuses to cut while ``origin/main`` carries
commits absent from ``origin/dev``. That guard turns a silent hazard into a hard
failure, but only at the *next* release -- the drift still persists for however
long passes before someone tries. This closes that window from the other side:
the reconciliation is waiting for review instead of waiting to be remembered.

Two constraints shape the design, both worth knowing before editing:

* **A pull request is mandatory.** The repository ruleset requires one, with an
  approving review, on both ``main`` and ``dev``, and blocks non-fast-forward
  pushes and deletion. This cannot push to ``dev`` and cannot merge its own
  pull request -- a human approval is the point. The job is to make sure the
  pull request *exists*.
* **A conflict is a normal outcome, not an error.** Release drift conflicts on
  ``CHANGELOG.md`` by construction (``main`` carries the stamped ``## [X.Y.Z]``
  heading while ``dev`` still has those entries under ``## [Unreleased]``), and
  binary assets conflict whenever both branches touched one. Neither is
  resolvable here: ``-X ours`` and ``-X theirs`` both silently discard real
  work. A conflict routes to the tracking issue and the run still exits zero,
  because a red run on every release trains people to ignore the signal.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

DEV_BRANCH = "dev"
MAIN_BRANCH = "main"

# The tracking issue is found by label rather than by title, so the title stays
# free to carry the live commit count.
LABEL = "back-merge"

# Deterministic per ``main`` head, which is what makes a re-run idempotent: the
# same drift resolves to the same branch name, so an existing branch is
# recognized rather than pushed over.
BRANCH_PREFIX = "rc-dev/chore/back-merge-main-"

# Embedded in every issue body and comment. A re-run that would say exactly the
# same thing finds its own marker and stays quiet, so an unresolved divergence
# does not accumulate one identical comment per scheduled run.
STATE_MARKER_PREFIX = "<!-- backmerge-state:"

# Set from ``BACKMERGE_DRY_RUN`` so the pull request that edits this workflow
# exercises it for real -- the fetch, the count, the merge, the conflict
# detection -- while every push, pull request and issue write is announced
# instead of performed. Without it, testing a change to this file would open a
# genuine back-merge pull request off the branch under review.
DRY_RUN = False


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Echo and run a command in the repo root, raising on non-zero exit."""
    print(f"$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=REPO_ROOT, check=True, **kwargs)


def capture(cmd: list[str]) -> str:
    """Run a command in the repo root and return its stripped stdout."""
    result = subprocess.run(
        cmd, cwd=REPO_ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def mutate(cmd: list[str]) -> int:
    """Run a command that changes remote or issue state, unless dry-running.

    Returns an exit code so callers can route a rejection to the tracking
    issue; a dry run reports success, since the point is to reach the code
    paths beyond it.
    """
    if DRY_RUN:
        print(f"[dry run] would run: {' '.join(cmd)}", flush=True)
        return 0
    return try_run(cmd)


def try_run(cmd: list[str]) -> int:
    """Run a command that is allowed to fail, returning its exit code.

    Used for the merge (a conflict is an expected outcome) and for ``gh pr
    create`` (which is denied outright when the repository forbids Actions from
    creating pull requests). Both route to the tracking issue instead of
    aborting the run.
    """
    print(f"$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=REPO_ROOT).returncode


def main_only_count() -> int:
    """How many commits ``origin/main`` carries that ``origin/dev`` does not."""
    return int(
        capture(
            ["git", "rev-list", "--count", f"origin/{DEV_BRANCH}..origin/{MAIN_BRANCH}"]
        )
    )


def main_head() -> str:
    """The short SHA of ``origin/main``."""
    return capture(["git", "rev-parse", "--short", f"origin/{MAIN_BRANCH}"])


def branch_for(sha: str) -> str:
    """The back-merge branch name for a given ``origin/main`` head."""
    return f"{BRANCH_PREFIX}{sha}"


def carried_commits() -> list[str]:
    """One ``<short-sha> <subject>`` line per commit being carried into ``dev``."""
    return capture(
        ["git", "log", "--format=%h %s", f"origin/{DEV_BRANCH}..origin/{MAIN_BRANCH}"]
    ).splitlines()


def signoff_trailer() -> str:
    """A DCO trailer for the merge commit, matching the configured git identity.

    The DCO workflow runs on every pull request with no path filter, so a merge
    commit without this fails the check on the very pull request this exists to
    open.
    """
    name = capture(["git", "config", "user.name"])
    email = capture(["git", "config", "user.email"])
    return f"Signed-off-by: {name} <{email}>"


def merge_message(behind: int, signoff: str) -> str:
    """The merge commit subject and its DCO trailer."""
    plural = "" if behind == 1 else "s"
    return f"chore: back-merge {MAIN_BRANCH} into {DEV_BRANCH} ({behind} commit{plural})\n\n{signoff}"


def attempt_merge(branch: str, message: str) -> list[str]:
    """Cut ``branch`` from ``dev`` and merge ``main`` into it.

    Returns the conflicting paths; an empty list means the merge is clean and
    the branch is ready to push.

    The direction is load-bearing. The head branch must contain ``dev`` plus
    ``main`` so the pull request's base can be ``dev``; merging the other way
    would produce a branch that cannot be proposed into ``dev`` at all.
    """
    run(["git", "checkout", "-B", branch, f"origin/{DEV_BRANCH}"])
    merge = ["git", "merge", "--no-ff", "-m", message, f"origin/{MAIN_BRANCH}"]
    if try_run(merge) == 0:
        return []
    conflicts = capture(["git", "diff", "--name-only", "--diff-filter=U"]).splitlines()
    run(["git", "merge", "--abort"])
    return conflicts


def remote_branch_exists(branch: str) -> bool:
    """Whether ``branch`` is already on the remote."""
    return bool(capture(["git", "ls-remote", "--heads", "origin", branch]))


def existing_pr(branch: str) -> str:
    """The number of any pull request already opened for ``branch``, or ``""``.

    Searched across every state: a closed back-merge pull request was closed by
    a human decision, and reopening it would be this workflow overruling them.
    """
    return capture(
        [
            "gh",
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "all",
            "--limit",
            "1",
            "--json",
            "number",
            "--jq",
            ".[0].number // empty",
        ]
    )


def open_tracking_issue() -> str:
    """The number of the open tracking issue, or ``""``."""
    return capture(
        [
            "gh",
            "issue",
            "list",
            "--label",
            LABEL,
            "--state",
            "open",
            "--limit",
            "1",
            "--json",
            "number",
            "--jq",
            ".[0].number // empty",
        ]
    )


def ensure_label() -> None:
    """Create the tracking label if it is absent.

    Idempotent, so the label needs no manual repository setup and a rename
    cannot leave this step failing on a missing label.
    """
    mutate(
        [
            "gh",
            "label",
            "create",
            LABEL,
            "--color",
            "fbca04",
            "--description",
            "origin/main carries commits absent from origin/dev",
            "--force",
        ]
    )


def issue_title(behind: int) -> str:
    """The tracking issue title, carrying the live commit count."""
    plural = "" if behind == 1 else "s"
    return (
        f"Back-merge {MAIN_BRANCH} into {DEV_BRANCH} ({behind} commit{plural} behind)"
    )


def state_marker(sha: str, behind: int, conflicts: list[str]) -> str:
    """A fingerprint of the drift, so an unchanged re-run posts nothing."""
    paths = ",".join(sorted(conflicts))
    return f"{STATE_MARKER_PREFIX} {sha} behind={behind} conflicts={paths} -->"


def already_reported(issue: str, marker: str) -> bool:
    """Whether the issue body or any of its comments already carries ``marker``."""
    seen = capture(
        [
            "gh",
            "issue",
            "view",
            issue,
            "--json",
            "body,comments",
            "--jq",
            ".body, (.comments[].body)",
        ]
    )
    return marker in seen


def pr_body(commits: list[str], behind: int, has_ci: bool) -> str:
    """The back-merge pull request body."""
    plural = "" if behind == 1 else "s"
    listing = "\n".join(f"- `{line}`" for line in commits)
    checks = (
        "This pull request was opened by a token that triggers workflows, so its checks run normally."
        if has_ci
        else (
            "**This pull request carries no CI checks.** It was opened by `GITHUB_TOKEN`, and GitHub "
            "deliberately does not trigger `on: pull_request` workflows for events raised by it — an "
            "unchecked pull request that merely *looks* green would be worse. To run them, close and "
            "reopen this pull request, or push any commit to its branch. Setting a `BACKMERGE_TOKEN` "
            "secret makes checks run on their own; see RELEASE.md."
        )
    )
    return f"""\
`origin/{MAIN_BRANCH}` carries {behind} commit{plural} that `origin/{DEV_BRANCH}` does not. Until they are back-merged, `{DEV_BRANCH}` is missing work that has already shipped, and `release.py release-pr` refuses to cut a release at all.

These commits reached `{MAIN_BRANCH}` outside the release flow — a hotfix, a docs fix, or anything else merged straight into the default branch.

## Commits being carried over

{listing}

## Checks

{checks}

---

Opened automatically by `.github/workflows/backmerge.yml`. The merge was clean; review it as you would any other pull request.
"""


def issue_body(
    sha: str,
    behind: int,
    branch: str,
    conflicts: list[str],
    commits: list[str],
    marker: str,
    run_url: str,
    reason: str,
) -> str:
    """The tracking issue body, for drift that could not become a pull request."""
    plural = "" if behind == 1 else "s"
    listing = "\n".join(f"- `{line}`" for line in commits)

    if conflicts:
        paths = "\n".join(f"- `{path}`" for path in conflicts)
        detail = f"""\
## Conflicting paths

{paths}

Nothing was pushed. Resolving a conflict is a human decision — `-X ours` and `-X theirs` both silently discard real work, so this workflow will not attempt it.
"""
        if "CHANGELOG.md" in conflicts:
            detail += """
`CHANGELOG.md` conflicts are the expected shape of *release* drift: `main` carries the stamped `## [X.Y.Z]` heading while `dev` still has those entries under `## [Unreleased]`. The resolution is stable — keep `main`'s stamped heading and reopen an empty `## [Unreleased]` above it.
"""
    else:
        detail = f"""\
The merge itself was clean. What failed was opening the pull request: {reason}
"""

    return f"""\
`origin/{MAIN_BRANCH}` is {behind} commit{plural} ahead of `origin/{DEV_BRANCH}`, and the back-merge could not be opened automatically.

Until this is reconciled, `release.py release-pr` refuses to cut a release, so this blocks the next one.

## Commits waiting to be carried over

{listing}

{detail}
## Resolving it by hand

```bash
git fetch origin {MAIN_BRANCH} {DEV_BRANCH}
git checkout -b {branch} origin/{DEV_BRANCH}
git merge origin/{MAIN_BRANCH}
# resolve, commit with a sign-off, then:
git push -u origin {branch}
gh pr create --base {DEV_BRANCH} --head {branch} \\
  --title "chore: back-merge {MAIN_BRANCH} into {DEV_BRANCH}"
```

Run: {run_url}

This issue closes on its own once `origin/{MAIN_BRANCH}` and `origin/{DEV_BRANCH}` are back in sync.

{marker}
"""


def track(
    sha: str,
    behind: int,
    branch: str,
    conflicts: list[str],
    commits: list[str],
    run_url: str,
    reason: str,
) -> None:
    """Open the tracking issue, or comment on the open one when the state changed."""
    ensure_label()
    marker = state_marker(sha, behind, conflicts)
    body = issue_body(sha, behind, branch, conflicts, commits, marker, run_url, reason)
    title = issue_title(behind)
    issue = open_tracking_issue()
    if not issue:
        mutate(
            [
                "gh",
                "issue",
                "create",
                "--title",
                title,
                "--label",
                LABEL,
                "--body",
                body,
            ]
        )
        return
    if already_reported(issue, marker):
        print(f"Issue #{issue} already describes this exact state; nothing to add.")
        return
    mutate(["gh", "issue", "comment", issue, "--body", body])
    # The title carries the live count, which is why the issue is found by label
    # rather than by title. A stale count in the title reads as a stale issue.
    mutate(["gh", "issue", "edit", issue, "--title", title])


def open_pr(branch: str, commits: list[str], behind: int, has_ci: bool) -> int:
    """Open the back-merge pull request. Returns the ``gh`` exit code."""
    plural = "" if behind == 1 else "s"
    return mutate(
        [
            "gh",
            "pr",
            "create",
            "--base",
            DEV_BRANCH,
            "--head",
            branch,
            "--title",
            f"chore: back-merge {MAIN_BRANCH} into {DEV_BRANCH} ({behind} commit{plural})",
            "--body",
            pr_body(commits, behind, has_ci),
        ]
    )


def main() -> int:
    global DRY_RUN
    DRY_RUN = os.environ.get("BACKMERGE_DRY_RUN", "").lower() == "true"
    if DRY_RUN:
        print("Dry run: no branch, pull request or issue will be written.")

    # Explicit refspecs, not `git fetch origin main dev`: `actions/checkout`
    # configures `remote.origin.fetch` for the one branch it checked out, and
    # under that a bare fetch updates FETCH_HEAD without ever creating
    # `refs/remotes/origin/dev` -- every range below would then fail to resolve.
    run(
        [
            "git",
            "fetch",
            "--quiet",
            "origin",
            f"+refs/heads/{MAIN_BRANCH}:refs/remotes/origin/{MAIN_BRANCH}",
            f"+refs/heads/{DEV_BRANCH}:refs/remotes/origin/{DEV_BRANCH}",
        ]
    )

    behind = main_only_count()
    run_url = os.environ.get("RUN_URL", "(not a workflow run)")
    has_ci = os.environ.get("BACKMERGE_HAS_CI", "").lower() == "true"

    if behind == 0:
        issue = open_tracking_issue()
        if issue:
            mutate(
                [
                    "gh",
                    "issue",
                    "close",
                    issue,
                    "--comment",
                    f"`origin/{MAIN_BRANCH}` and `origin/{DEV_BRANCH}` are back in sync. Closing automatically.",
                ]
            )
        print(
            f"origin/{DEV_BRANCH} contains every commit on origin/{MAIN_BRANCH}; "
            "nothing to back-merge."
        )
        return 0

    sha = main_head()
    branch = branch_for(sha)
    commits = carried_commits()
    print(f"origin/{MAIN_BRANCH} is {behind} commit(s) ahead at {sha}.")

    # Idempotency, in the order the states can occur. A pull request that already
    # covers this exact `main` head is the finished outcome -- including a closed
    # one, which a human closed on purpose.
    pr = existing_pr(branch)
    if pr:
        print(f"Pull request #{pr} already covers {sha}; leaving it alone.")
        return 0

    if remote_branch_exists(branch):
        # A previous run pushed the branch but did not get as far as the pull
        # request. Finish the job without touching the branch: the ruleset
        # blocks non-fast-forward pushes, and rewriting a branch under review
        # destroys the incremental diff a reviewer is working through.
        print(f"Branch {branch} is already pushed; opening its pull request.")
        if open_pr(branch, commits, behind, has_ci) != 0:
            track(sha, behind, branch, [], commits, run_url, "`gh pr create` failed.")
        return 0

    conflicts = attempt_merge(branch, merge_message(behind, signoff_trailer()))
    if conflicts:
        print(f"Merge conflicts in {len(conflicts)} path(s); pushing nothing.")
        track(sha, behind, branch, conflicts, commits, run_url, "")
        return 0

    mutate(["git", "push", "origin", branch])
    if open_pr(branch, commits, behind, has_ci) != 0:
        track(
            sha,
            behind,
            branch,
            [],
            commits,
            run_url,
            "`gh pr create` was rejected. The usual cause is the repository "
            "forbidding GitHub Actions from creating pull requests "
            "(Settings -> Actions -> General). The branch is pushed and ready.",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
