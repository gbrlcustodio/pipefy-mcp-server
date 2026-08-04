"""Tests for .github/workflows/scripts/backmerge.py decision logic.

The workflow itself is three steps of YAML; every decision worth getting wrong
lives in the script. What these cover is the part that is expensive to discover
in production: the merge direction, the idempotency rules that stop a scheduled
run from filing a duplicate every morning, and the dry run that keeps the pull
request editing this workflow from opening a real back-merge.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "scripts"
    / "backmerge.py"
)
_spec = importlib.util.spec_from_file_location("backmerge", _SCRIPT)
assert _spec and _spec.loader
_backmerge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_backmerge)


@pytest.fixture(autouse=True)
def _forbid_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if a test reaches a real ``git``/``gh`` command.

    These tests exercise back-merge *decisions*, not the commands they
    authorize. A guard that stopped working would otherwise let a test fall
    through into a real ``git checkout``/``git merge`` against the working tree,
    or a real ``gh issue create`` against the repository. Tests that need a
    command stub one explicitly; their ``setattr`` wins over this.
    """

    def _forbid(cmd, **kwargs):
        raise AssertionError(f"test reached a real subprocess: {cmd}")

    monkeypatch.setattr(_backmerge, "run", _forbid)
    monkeypatch.setattr(_backmerge, "capture", _forbid)
    monkeypatch.setattr(_backmerge, "try_run", _forbid)


@pytest.fixture(autouse=True)
def _reset_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the module-level dry-run flag from leaking between tests."""
    monkeypatch.setattr(_backmerge, "DRY_RUN", False)


def test_main_only_count_reads_the_rev_list_range(monkeypatch) -> None:
    # The range must be dev..main. Reversed, it would count dev's own work and
    # propose a back-merge on every commit that lands on dev.
    seen: list[list[str]] = []
    monkeypatch.setattr(_backmerge, "capture", lambda cmd: (seen.append(cmd), "3")[1])
    assert _backmerge.main_only_count() == 3
    assert seen == [["git", "rev-list", "--count", "origin/dev..origin/main"]]


def test_branch_name_is_deterministic_per_main_head() -> None:
    # Idempotency rests on this: the same drift must resolve to the same branch
    # name, or every run pushes a new branch and opens a duplicate.
    assert _backmerge.branch_for("abc1234") == "rc-dev/chore/back-merge-main-abc1234"
    assert _backmerge.branch_for("abc1234") == _backmerge.branch_for("abc1234")
    assert _backmerge.branch_for("abc1234") != _backmerge.branch_for("def5678")


def test_merge_cuts_from_dev_and_merges_main(monkeypatch) -> None:
    # The head branch must contain dev plus main so the PR's base can be dev.
    # Cutting from main instead would produce a branch that cannot be proposed
    # into dev at all.
    seen: list[list[str]] = []
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: seen.append(cmd))
    monkeypatch.setattr(_backmerge, "try_run", lambda cmd: (seen.append(cmd), 0)[1])

    assert _backmerge.attempt_merge("some-branch", "msg") == []
    assert seen[0] == ["git", "checkout", "-B", "some-branch", "origin/dev"]
    assert seen[1] == ["git", "merge", "--no-ff", "-m", "msg", "origin/main"]


def test_merge_conflict_collects_paths_then_aborts(monkeypatch) -> None:
    # The paths must be read *before* the abort: `git merge --abort` clears the
    # unmerged index, so reading them afterwards would always return nothing and
    # the tracking issue would name no files.
    seen: list[list[str]] = []
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: seen.append(cmd))
    monkeypatch.setattr(_backmerge, "try_run", lambda cmd: (seen.append(cmd), 1)[1])
    monkeypatch.setattr(
        _backmerge,
        "capture",
        lambda cmd: (seen.append(cmd), "CHANGELOG.md\ndocs/banner.png")[1],
    )

    assert _backmerge.attempt_merge("b", "msg") == ["CHANGELOG.md", "docs/banner.png"]
    diff_at = seen.index(["git", "diff", "--name-only", "--diff-filter=U"])
    abort_at = seen.index(["git", "merge", "--abort"])
    assert diff_at < abort_at


def test_merge_message_carries_a_signoff() -> None:
    # The DCO workflow runs on every pull request with no path filter, so a
    # merge commit without this fails the check on the pull request this exists
    # to open.
    msg = _backmerge.merge_message(9, "Signed-off-by: bot <bot@example.com>")
    assert msg.startswith("chore: back-merge main into dev (9 commits)")
    assert msg.endswith("Signed-off-by: bot <bot@example.com>")


def test_merge_message_singular() -> None:
    assert "(1 commit)" in _backmerge.merge_message(1, "Signed-off-by: x <y>")


def test_state_marker_is_order_independent() -> None:
    # Conflicting paths arrive in git's order, which is not stable across
    # versions. Unsorted, a re-run would look like a new state and comment again.
    a = _backmerge.state_marker("abc1234", 2, ["b.md", "a.md"])
    b = _backmerge.state_marker("abc1234", 2, ["a.md", "b.md"])
    assert a == b


def test_state_marker_changes_with_the_drift() -> None:
    base = _backmerge.state_marker("abc1234", 2, ["a.md"])
    assert base != _backmerge.state_marker("def5678", 2, ["a.md"])
    assert base != _backmerge.state_marker("abc1234", 3, ["a.md"])
    assert base != _backmerge.state_marker("abc1234", 2, ["a.md", "b.md"])


def test_existing_pr_search_spans_every_state(monkeypatch) -> None:
    # A closed back-merge pull request was closed by a human decision. Searching
    # open-only would reopen that argument on the next scheduled run.
    seen: list[list[str]] = []
    monkeypatch.setattr(_backmerge, "capture", lambda cmd: (seen.append(cmd), "")[1])
    _backmerge.existing_pr("some-branch")
    assert "--state" in seen[0]
    assert seen[0][seen[0].index("--state") + 1] == "all"


def test_pr_body_states_plainly_when_there_are_no_checks() -> None:
    body = _backmerge.pr_body(["abc1234 docs: fix"], 1, has_ci=False)
    assert "carries no CI checks" in body
    assert "close and reopen" in body.lower()
    assert "`abc1234 docs: fix`" in body


def test_pr_body_does_not_claim_missing_checks_when_a_token_is_set() -> None:
    body = _backmerge.pr_body(["abc1234 docs: fix"], 1, has_ci=True)
    assert "carries no CI checks" not in body
    assert "checks run normally" in body


def test_issue_body_names_the_conflicting_paths() -> None:
    body = _backmerge.issue_body(
        "abc1234",
        2,
        "rc-dev/chore/back-merge-main-abc1234",
        ["docs/images/banner.png"],
        ["abc1234 docs: banner"],
        "<!-- marker -->",
        "https://example.test/run/1",
        "",
    )
    assert "`docs/images/banner.png`" in body
    assert "rc-dev/chore/back-merge-main-abc1234" in body
    assert "<!-- marker -->" in body
    # The CHANGELOG recipe is wrong for a binary conflict; it must stay
    # conditional on CHANGELOG.md actually being one of the conflicting paths.
    assert "## [Unreleased]" not in body


def test_issue_body_adds_the_changelog_recipe_only_when_it_conflicts() -> None:
    body = _backmerge.issue_body(
        "abc1234",
        2,
        "branch",
        ["CHANGELOG.md"],
        ["abc1234 chore: release"],
        "<!-- marker -->",
        "https://example.test/run/1",
        "",
    )
    assert "## [Unreleased]" in body


def test_issue_body_explains_a_clean_merge_that_could_not_be_proposed() -> None:
    body = _backmerge.issue_body(
        "abc1234",
        1,
        "branch",
        [],
        ["abc1234 docs: fix"],
        "<!-- marker -->",
        "https://example.test/run/1",
        "`gh pr create` was rejected.",
    )
    assert "The merge itself was clean" in body
    assert "`gh pr create` was rejected." in body
    assert "Conflicting paths" not in body


def test_in_sync_closes_the_tracking_issue(monkeypatch) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: seen.append(cmd))
    monkeypatch.setattr(_backmerge, "main_only_count", lambda: 0)
    monkeypatch.setattr(_backmerge, "open_tracking_issue", lambda: "42")
    monkeypatch.setattr(_backmerge, "try_run", lambda cmd: (seen.append(cmd), 0)[1])

    assert _backmerge.main() == 0
    close = [c for c in seen if c[:3] == ["gh", "issue", "close"]]
    assert close and close[0][3] == "42"


def test_in_sync_with_no_open_issue_does_nothing(monkeypatch) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: seen.append(cmd))
    monkeypatch.setattr(_backmerge, "main_only_count", lambda: 0)
    monkeypatch.setattr(_backmerge, "open_tracking_issue", lambda: "")

    assert _backmerge.main() == 0
    # Explicit refspecs, not bare branch names: `actions/checkout` configures
    # `remote.origin.fetch` for the one branch it checked out, and under that a
    # bare fetch updates FETCH_HEAD without creating `refs/remotes/origin/dev`.
    assert seen == [
        [
            "git",
            "fetch",
            "--quiet",
            "origin",
            "+refs/heads/main:refs/remotes/origin/main",
            "+refs/heads/dev:refs/remotes/origin/dev",
        ]
    ]


def test_an_existing_pull_request_stops_the_run(monkeypatch) -> None:
    # Re-running against an unchanged main head must not open a second pull
    # request, push over the branch, or file a duplicate issue.
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: None)
    monkeypatch.setattr(_backmerge, "main_only_count", lambda: 2)
    monkeypatch.setattr(_backmerge, "main_head", lambda: "abc1234")
    monkeypatch.setattr(_backmerge, "carried_commits", lambda: ["abc1234 docs: fix"])
    monkeypatch.setattr(_backmerge, "existing_pr", lambda branch: "77")

    def _explode(*args, **kwargs):
        raise AssertionError("must not act while a pull request already exists")

    monkeypatch.setattr(_backmerge, "attempt_merge", _explode)
    monkeypatch.setattr(_backmerge, "open_pr", _explode)
    monkeypatch.setattr(_backmerge, "track", _explode)

    assert _backmerge.main() == 0


def test_a_pushed_branch_without_a_pull_request_is_not_pushed_again(
    monkeypatch,
) -> None:
    # The ruleset blocks non-fast-forward pushes, and rewriting a branch under
    # review destroys the incremental diff. Finish the job, do not redo it.
    calls: list[str] = []
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: calls.append(cmd[0]))
    monkeypatch.setattr(_backmerge, "main_only_count", lambda: 2)
    monkeypatch.setattr(_backmerge, "main_head", lambda: "abc1234")
    monkeypatch.setattr(_backmerge, "carried_commits", lambda: ["abc1234 docs: fix"])
    monkeypatch.setattr(_backmerge, "existing_pr", lambda branch: "")
    monkeypatch.setattr(_backmerge, "remote_branch_exists", lambda branch: True)

    def _explode(*args, **kwargs):
        raise AssertionError("must not re-merge or re-push an existing branch")

    monkeypatch.setattr(_backmerge, "attempt_merge", _explode)
    opened: list[str] = []
    monkeypatch.setattr(
        _backmerge, "open_pr", lambda b, c, n, ci: (opened.append(b), 0)[1]
    )

    assert _backmerge.main() == 0
    assert opened == ["rc-dev/chore/back-merge-main-abc1234"]


def test_a_conflict_pushes_nothing_and_tracks(monkeypatch) -> None:
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: None)
    mutated: list[list[str]] = []
    monkeypatch.setattr(_backmerge, "mutate", lambda cmd: (mutated.append(cmd), 0)[1])
    monkeypatch.setattr(_backmerge, "main_only_count", lambda: 2)
    monkeypatch.setattr(_backmerge, "main_head", lambda: "abc1234")
    monkeypatch.setattr(_backmerge, "carried_commits", lambda: ["abc1234 docs: fix"])
    monkeypatch.setattr(_backmerge, "existing_pr", lambda branch: "")
    monkeypatch.setattr(_backmerge, "remote_branch_exists", lambda branch: False)
    monkeypatch.setattr(_backmerge, "signoff_trailer", lambda: "Signed-off-by: b <b@e>")
    monkeypatch.setattr(_backmerge, "attempt_merge", lambda b, m: ["CHANGELOG.md"])

    tracked: list[list[str]] = []
    monkeypatch.setattr(
        _backmerge,
        "track",
        lambda sha, behind, branch, conflicts, commits, url, reason: tracked.append(
            conflicts
        ),
    )

    def _explode(*args, **kwargs):
        raise AssertionError("must not open a pull request for a conflicted merge")

    monkeypatch.setattr(_backmerge, "open_pr", _explode)

    assert _backmerge.main() == 0
    assert tracked == [["CHANGELOG.md"]]
    assert not [cmd for cmd in mutated if "push" in cmd]


def test_a_rejected_pull_request_falls_through_to_the_issue(monkeypatch) -> None:
    # If the repository forbids Actions from creating pull requests, the drift
    # must still surface somewhere rather than vanishing into a green run.
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: None)
    monkeypatch.setattr(_backmerge, "mutate", lambda cmd: 0)
    monkeypatch.setattr(_backmerge, "main_only_count", lambda: 2)
    monkeypatch.setattr(_backmerge, "main_head", lambda: "abc1234")
    monkeypatch.setattr(_backmerge, "carried_commits", lambda: ["abc1234 docs: fix"])
    monkeypatch.setattr(_backmerge, "existing_pr", lambda branch: "")
    monkeypatch.setattr(_backmerge, "remote_branch_exists", lambda branch: False)
    monkeypatch.setattr(_backmerge, "signoff_trailer", lambda: "Signed-off-by: b <b@e>")
    monkeypatch.setattr(_backmerge, "attempt_merge", lambda b, m: [])
    monkeypatch.setattr(_backmerge, "open_pr", lambda b, c, n, ci: 1)

    reasons: list[str] = []
    monkeypatch.setattr(
        _backmerge,
        "track",
        lambda sha, behind, branch, conflicts, commits, url, reason: reasons.append(
            reason
        ),
    )

    assert _backmerge.main() == 0
    assert reasons and "gh pr create" in reasons[0]


def test_track_stays_silent_when_the_state_is_unchanged(monkeypatch) -> None:
    # The scheduled run fires daily. Without this, an unresolved divergence
    # accumulates one identical comment per morning.
    monkeypatch.setattr(_backmerge, "ensure_label", lambda: None)
    monkeypatch.setattr(_backmerge, "open_tracking_issue", lambda: "42")
    monkeypatch.setattr(_backmerge, "already_reported", lambda issue, marker: True)

    def _explode(cmd):
        raise AssertionError("must not comment when nothing changed")

    monkeypatch.setattr(_backmerge, "mutate", _explode)
    _backmerge.track("abc1234", 2, "branch", ["a.md"], ["abc1234 x"], "url", "")


def test_track_comments_when_the_state_changed(monkeypatch) -> None:
    monkeypatch.setattr(_backmerge, "ensure_label", lambda: None)
    monkeypatch.setattr(_backmerge, "open_tracking_issue", lambda: "42")
    monkeypatch.setattr(_backmerge, "already_reported", lambda issue, marker: False)
    seen: list[list[str]] = []
    monkeypatch.setattr(_backmerge, "mutate", lambda cmd: (seen.append(cmd), 0)[1])

    _backmerge.track("abc1234", 3, "branch", ["a.md"], ["abc1234 x"], "url", "")
    assert seen[0][:3] == ["gh", "issue", "comment"]
    assert seen[0][3] == "42"


def test_track_opens_the_issue_when_none_is_open(monkeypatch) -> None:
    monkeypatch.setattr(_backmerge, "ensure_label", lambda: None)
    monkeypatch.setattr(_backmerge, "open_tracking_issue", lambda: "")
    seen: list[list[str]] = []
    monkeypatch.setattr(_backmerge, "mutate", lambda cmd: (seen.append(cmd), 0)[1])

    _backmerge.track("abc1234", 3, "branch", ["a.md"], ["abc1234 x"], "url", "")
    assert seen[0][:3] == ["gh", "issue", "create"]
    assert "--label" in seen[0]
    assert seen[0][seen[0].index("--label") + 1] == _backmerge.LABEL


def test_dry_run_announces_instead_of_writing(monkeypatch, capsys) -> None:
    # The pull request editing this workflow must not open a real back-merge.
    monkeypatch.setattr(_backmerge, "DRY_RUN", True)

    def _explode(cmd):
        raise AssertionError("dry run must not reach a real command")

    monkeypatch.setattr(_backmerge, "try_run", _explode)
    assert _backmerge.mutate(["gh", "pr", "create"]) == 0
    assert "[dry run]" in capsys.readouterr().out
