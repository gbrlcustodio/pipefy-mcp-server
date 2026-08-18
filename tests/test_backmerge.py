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


def test_pr_body_demands_a_merge_commit() -> None:
    # A squash or rebase drops the second parent, so `dev` gains the content but
    # never the ancestry: the count stays put, `release-pr` stays blocked, and the
    # next run reopens the same pull request. #577 was squash-merged and the drift
    # did not move, which is how this was found.
    body = _backmerge.pr_body(["abc1234 docs: fix"], 9, has_ci=False)
    assert "Create a merge commit" in body
    assert "does not converge" in body


def test_pr_body_flags_an_ancestry_only_merge() -> None:
    listing = ["abc1234 docs: fix"]
    assert "changes no files" in _backmerge.pr_body(
        listing, 9, has_ci=False, ancestry_only=True
    )
    assert "changes no files" not in _backmerge.pr_body(listing, 9, has_ci=False)


def test_ancestry_only_compares_the_merge_against_dev(monkeypatch) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr(_backmerge, "try_run", lambda cmd: (seen.append(cmd), 0)[1])
    assert _backmerge.is_ancestry_only()
    assert seen == [["git", "diff", "--quiet", "origin/dev", "HEAD"]]

    monkeypatch.setattr(_backmerge, "try_run", lambda cmd: 1)
    assert not _backmerge.is_ancestry_only()


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
        "The merge was clean, but `gh pr create` was rejected.",
    )
    # With no conflicts the reason stands on its own, so each caller can say what
    # actually happened -- a rejected pull request, a failed push, or a closed
    # one -- instead of inheriting one hardcoded explanation that fits only some.
    assert "The merge was clean, but `gh pr create` was rejected." in body
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


def test_an_open_pull_request_stops_the_run(monkeypatch) -> None:
    # Re-running against an unchanged main head must not open a second pull
    # request, push over the branch, or file a duplicate issue.
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: None)
    monkeypatch.setattr(_backmerge, "main_only_count", lambda: 2)
    monkeypatch.setattr(_backmerge, "main_head", lambda: "abc1234")
    monkeypatch.setattr(_backmerge, "carried_commits", lambda: ["abc1234 docs: fix"])
    monkeypatch.setattr(_backmerge, "existing_pr", lambda branch: ("77", "OPEN"))

    def _explode(*args, **kwargs):
        raise AssertionError("must not act while a pull request is already open")

    monkeypatch.setattr(_backmerge, "attempt_merge", _explode)
    monkeypatch.setattr(_backmerge, "open_pr", _explode)
    monkeypatch.setattr(_backmerge, "track", _explode)

    assert _backmerge.main() == 0


def test_a_closed_pull_request_still_surfaces_the_drift(monkeypatch) -> None:
    # #564 and #565 were both closed without merging, and the divergence then sat
    # unnoticed for days. Treating a closed pull request as "handled" reproduces
    # exactly that: no pull request, no issue, and a green run.
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: None)
    monkeypatch.setattr(_backmerge, "main_only_count", lambda: 2)
    monkeypatch.setattr(_backmerge, "main_head", lambda: "abc1234")
    monkeypatch.setattr(_backmerge, "carried_commits", lambda: ["abc1234 docs: fix"])
    monkeypatch.setattr(_backmerge, "existing_pr", lambda branch: ("77", "CLOSED"))

    def _explode(*args, **kwargs):
        raise AssertionError("must not reopen or re-push a closed pull request")

    monkeypatch.setattr(_backmerge, "attempt_merge", _explode)
    monkeypatch.setattr(_backmerge, "open_pr", _explode)

    reasons: list[str] = []
    monkeypatch.setattr(
        _backmerge,
        "track",
        lambda sha, behind, branch, conflicts, commits, url, reason: (
            reasons.append(reason),
            True,
        )[1],
    )

    assert _backmerge.main() == 0
    assert reasons and "#77" in reasons[0]
    assert "closed without" in reasons[0]


def _merged_then_no_repair(branch: str) -> tuple[str, str]:
    """The original back-merge is merged; no ancestry repair exists yet."""
    return (
        ("", "") if branch.endswith(_backmerge.RECOVERY_SUFFIX) else ("577", "MERGED")
    )


def test_a_squashed_back_merge_opens_the_ancestry_repair(monkeypatch) -> None:
    # Merged, yet dev still does not contain main. That only happens when the
    # pull request was squashed or rebased: the second parent is discarded, so
    # the content lands but the ancestry never does and the count cannot reach
    # zero. #577 was squash-merged and the drift stayed at 9. The content being
    # already on dev is exactly what makes the repair safe to build.
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: None)
    monkeypatch.setattr(_backmerge, "main_only_count", lambda: 9)
    monkeypatch.setattr(_backmerge, "main_head", lambda: "abc1234")
    monkeypatch.setattr(_backmerge, "carried_commits", lambda: ["abc1234 docs: fix"])
    monkeypatch.setattr(_backmerge, "dco_mismatches", lambda: [])
    monkeypatch.setattr(_backmerge, "existing_pr", _merged_then_no_repair)
    monkeypatch.setattr(_backmerge, "remote_branch_exists", lambda branch: False)
    monkeypatch.setattr(_backmerge, "signoff_trailer", lambda: "Signed-off-by: b <b@e>")
    monkeypatch.setattr(_backmerge, "supersede_tracking_issue", lambda branch: None)

    def _explode(*args, **kwargs):
        raise AssertionError("a 3-way merge duplicates text dev already carries")

    monkeypatch.setattr(_backmerge, "attempt_merge", _explode)
    monkeypatch.setattr(_backmerge, "open_pr", _explode)

    merged: list[str] = []
    monkeypatch.setattr(
        _backmerge,
        "attempt_ancestry_merge",
        lambda branch, message: (merged.append(branch), True)[1],
    )
    pushed: list[list[str]] = []
    monkeypatch.setattr(_backmerge, "mutate", lambda cmd: (pushed.append(cmd), 0)[1])
    opened: list[tuple[str, str]] = []
    monkeypatch.setattr(
        _backmerge,
        "open_recovery_pr",
        lambda b, pr, n, c, ci, dco: (opened.append((b, pr)), 0)[1],
    )
    monkeypatch.setattr(
        _backmerge,
        "track",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("a repair was opened; there is nothing to track")
        ),
    )

    expected = "rc-dev/chore/back-merge-main-abc1234-ancestry"
    assert _backmerge.main() == 0
    assert merged == [expected]
    assert pushed == [["git", "push", "origin", expected]]
    assert opened == [(expected, "577")]


def test_an_open_ancestry_repair_is_left_alone(monkeypatch) -> None:
    # Same idempotency rule as the ordinary back-merge: the branch is keyed to
    # the same main head, so a scheduled re-run finds its own work rather than
    # pushing over a branch a reviewer is reading.
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: None)
    monkeypatch.setattr(_backmerge, "main_only_count", lambda: 9)
    monkeypatch.setattr(_backmerge, "main_head", lambda: "abc1234")
    monkeypatch.setattr(_backmerge, "carried_commits", lambda: ["abc1234 docs: fix"])
    monkeypatch.setattr(_backmerge, "dco_mismatches", lambda: [])
    monkeypatch.setattr(
        _backmerge,
        "existing_pr",
        lambda branch: ("606", "OPEN")
        if branch.endswith(_backmerge.RECOVERY_SUFFIX)
        else ("577", "MERGED"),
    )

    def _explode(*args, **kwargs):
        raise AssertionError("must not rebuild a repair that is already proposed")

    monkeypatch.setattr(_backmerge, "attempt_ancestry_merge", _explode)
    monkeypatch.setattr(_backmerge, "open_recovery_pr", _explode)
    monkeypatch.setattr(_backmerge, "track", _explode)

    assert _backmerge.main() == 0


def test_a_squashed_ancestry_repair_stops_instead_of_looping(monkeypatch) -> None:
    # Squashing the repair leaves the count exactly where it was. Opening a
    # third pull request keyed to the same head would loop, so the automation
    # stops here and hands the decision back with the commands to finish it.
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: None)
    monkeypatch.setattr(_backmerge, "main_only_count", lambda: 9)
    monkeypatch.setattr(_backmerge, "main_head", lambda: "abc1234")
    monkeypatch.setattr(_backmerge, "carried_commits", lambda: ["abc1234 docs: fix"])
    monkeypatch.setattr(_backmerge, "dco_mismatches", lambda: [])
    monkeypatch.setattr(
        _backmerge,
        "existing_pr",
        lambda branch: ("606", "MERGED")
        if branch.endswith(_backmerge.RECOVERY_SUFFIX)
        else ("577", "MERGED"),
    )

    def _explode(*args, **kwargs):
        raise AssertionError("must not open a third pull request for one head")

    monkeypatch.setattr(_backmerge, "attempt_ancestry_merge", _explode)
    monkeypatch.setattr(_backmerge, "open_recovery_pr", _explode)

    recorded: list[tuple[str, str]] = []
    monkeypatch.setattr(
        _backmerge,
        "track",
        lambda sha, behind, branch, conflicts, commits, url, reason: (
            recorded.append((branch, reason)),
            True,
        )[1],
    )

    assert _backmerge.main() == 0
    branch, reason = recorded[0]
    assert branch == "rc-dev/chore/back-merge-main-abc1234-ancestry"
    assert "#606 is MERGED" in reason
    assert "Create a merge commit" in reason


def test_a_failed_ancestry_merge_pushes_nothing_and_tracks(monkeypatch) -> None:
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: None)
    monkeypatch.setattr(_backmerge, "main_only_count", lambda: 9)
    monkeypatch.setattr(_backmerge, "main_head", lambda: "abc1234")
    monkeypatch.setattr(_backmerge, "carried_commits", lambda: ["abc1234 docs: fix"])
    monkeypatch.setattr(_backmerge, "dco_mismatches", lambda: [])
    monkeypatch.setattr(_backmerge, "existing_pr", _merged_then_no_repair)
    monkeypatch.setattr(_backmerge, "remote_branch_exists", lambda branch: False)
    monkeypatch.setattr(_backmerge, "signoff_trailer", lambda: "Signed-off-by: b <b@e>")
    monkeypatch.setattr(_backmerge, "attempt_ancestry_merge", lambda b, m: False)
    monkeypatch.setattr(
        _backmerge,
        "mutate",
        lambda cmd: (_ for _ in ()).throw(
            AssertionError("nothing may be pushed when the merge failed")
        ),
    )
    reasons: list[str] = []
    monkeypatch.setattr(
        _backmerge,
        "track",
        lambda sha, behind, branch, conflicts, commits, url, reason: (
            reasons.append(reason),
            True,
        )[1],
    )

    assert _backmerge.main() == 0
    assert "could not be built" in reasons[0]
    assert "Nothing was pushed" in reasons[0]


def test_the_ancestry_merge_takes_no_files_from_main(monkeypatch) -> None:
    # `-s ours` is the whole point: dev's tree is already current, and a 3-way
    # merge would duplicate paragraphs it already carries. Pin the argv, because
    # dropping the strategy silently turns this into the merge it must not be.
    argv: list[list[str]] = []
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: None)
    monkeypatch.setattr(_backmerge, "try_run", lambda cmd: (argv.append(cmd), 0)[1])

    assert _backmerge.attempt_ancestry_merge("branch", "message") is True
    assert argv == [
        ["git", "merge", "-s", "ours", "--no-ff", "-m", "message", "origin/main"]
    ]


def test_the_ancestry_repair_branch_is_keyed_to_the_main_head() -> None:
    assert (
        _backmerge.recovery_branch_for("abc1234")
        == "rc-dev/chore/back-merge-main-abc1234-ancestry"
    )
    # Distinct from the branch whose pull request is already merged, or the
    # repair would collide with it and be recognized as handled.
    assert _backmerge.recovery_branch_for("abc1234") != _backmerge.branch_for("abc1234")


def test_dco_mismatches_reports_author_and_signoff_disagreement(monkeypatch) -> None:
    # A squash rewrites the author to the GitHub profile identity while the
    # trailer stays as written, so the two disagree by name alone -- same email,
    # different name. The commit passed DCO on its own pull request; the merge
    # is what broke it.
    record = (
        "7052d6b\x1fAda L <a@example.com>\x1fAda <a@example.com>\x1e"
        "9447880\x1fmocha06 <m@e>\x1fmocha06 <m@e>\x1e"
        "deadbee\x1fNo Signoff <n@e>\x1f\x1e"
    )
    monkeypatch.setattr(_backmerge, "capture", lambda cmd: record)

    found = _backmerge.dco_mismatches()
    assert len(found) == 2
    assert "7052d6b" in found[0] and "signed off by" in found[0]
    # A matching author and sign-off is not a finding.
    assert not any("9447880" in line for line in found)
    assert "no sign-off" in found[1]


def test_dco_mismatches_skips_merge_commits(monkeypatch) -> None:
    # dco-check runs with --no-merges, so flagging a merge commit here would
    # promise a failure that never comes.
    argv: list[list[str]] = []
    monkeypatch.setattr(_backmerge, "capture", lambda cmd: (argv.append(cmd), "")[1])

    assert _backmerge.dco_mismatches() == []
    assert "--no-merges" in argv[0]


def test_dco_section_is_silent_when_every_commit_matches() -> None:
    assert _backmerge.dco_section([]) == ""
    assert "Expect the DCO check to fail" in _backmerge.dco_section(["`abc` author"])


def test_the_recovery_pull_request_body_demands_a_merge_commit() -> None:
    body = _backmerge.recovery_pr_body("577", 9, ["abc1234 docs: fix"], True, [])
    assert "Create a merge commit" in body
    assert "-s ours" in body
    # The reviewer's one-line check that it really takes nothing.
    assert "git diff origin/dev" in body
    assert "#577" in body


def test_a_pushed_branch_without_a_pull_request_is_not_pushed_again(
    monkeypatch,
) -> None:
    # The ruleset blocks non-fast-forward pushes, and rewriting a branch under
    # review destroys the incremental diff. Finish the job, do not redo it.
    calls: list[str] = []
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: calls.append(cmd[0]))
    monkeypatch.setattr(_backmerge, "main_only_count", lambda: 2)
    monkeypatch.setattr(_backmerge, "dco_mismatches", lambda: [])
    monkeypatch.setattr(_backmerge, "main_head", lambda: "abc1234")
    monkeypatch.setattr(_backmerge, "carried_commits", lambda: ["abc1234 docs: fix"])
    monkeypatch.setattr(_backmerge, "existing_pr", lambda branch: ("", ""))
    monkeypatch.setattr(_backmerge, "remote_branch_exists", lambda branch: True)
    monkeypatch.setattr(_backmerge, "open_tracking_issue", lambda: "")

    def _explode(*args, **kwargs):
        raise AssertionError("must not re-merge or re-push an existing branch")

    monkeypatch.setattr(_backmerge, "attempt_merge", _explode)
    opened: list[str] = []
    monkeypatch.setattr(
        _backmerge,
        "open_pr",
        lambda b, c, n, ci, ao=False, dco=None: (opened.append(b), 0)[1],
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
    monkeypatch.setattr(_backmerge, "existing_pr", lambda branch: ("", ""))
    monkeypatch.setattr(_backmerge, "remote_branch_exists", lambda branch: False)
    monkeypatch.setattr(_backmerge, "signoff_trailer", lambda: "Signed-off-by: b <b@e>")
    monkeypatch.setattr(_backmerge, "attempt_merge", lambda b, m: ["CHANGELOG.md"])

    tracked: list[list[str]] = []
    monkeypatch.setattr(
        _backmerge,
        "track",
        lambda sha, behind, branch, conflicts, commits, url, reason: (
            tracked.append(conflicts),
            True,
        )[1],
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
    monkeypatch.setattr(_backmerge, "dco_mismatches", lambda: [])
    monkeypatch.setattr(_backmerge, "main_head", lambda: "abc1234")
    monkeypatch.setattr(_backmerge, "carried_commits", lambda: ["abc1234 docs: fix"])
    monkeypatch.setattr(_backmerge, "existing_pr", lambda branch: ("", ""))
    monkeypatch.setattr(_backmerge, "remote_branch_exists", lambda branch: False)
    monkeypatch.setattr(_backmerge, "signoff_trailer", lambda: "Signed-off-by: b <b@e>")
    monkeypatch.setattr(_backmerge, "attempt_merge", lambda b, m: [])
    monkeypatch.setattr(_backmerge, "is_ancestry_only", lambda: False)
    monkeypatch.setattr(
        _backmerge, "open_pr", lambda b, c, n, ci, ao=False, dco=None: 1
    )

    reasons: list[str] = []
    monkeypatch.setattr(
        _backmerge,
        "track",
        lambda sha, behind, branch, conflicts, commits, url, reason: (
            reasons.append(reason),
            True,
        )[1],
    )

    assert _backmerge.main() == 0
    assert reasons and "gh pr create" in reasons[0]


def test_a_failed_tracking_issue_write_fails_the_run(monkeypatch) -> None:
    # Exiting zero on a conflict is only defensible while the tracking issue is
    # the compensating signal. If that write also fails, Actions would otherwise
    # stay green with no pull request and no issue -- the silent drift this
    # workflow exists to end.
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: None)
    monkeypatch.setattr(_backmerge, "main_only_count", lambda: 2)
    monkeypatch.setattr(_backmerge, "main_head", lambda: "abc1234")
    monkeypatch.setattr(_backmerge, "carried_commits", lambda: ["abc1234 docs: fix"])
    monkeypatch.setattr(_backmerge, "existing_pr", lambda branch: ("", ""))
    monkeypatch.setattr(_backmerge, "remote_branch_exists", lambda branch: False)
    monkeypatch.setattr(_backmerge, "signoff_trailer", lambda: "Signed-off-by: b <b@e>")
    monkeypatch.setattr(_backmerge, "attempt_merge", lambda b, m: ["CHANGELOG.md"])
    monkeypatch.setattr(_backmerge, "ensure_label", lambda: None)
    monkeypatch.setattr(_backmerge, "open_tracking_issue", lambda: "")
    # `gh issue create` rejected.
    monkeypatch.setattr(_backmerge, "mutate", lambda cmd: 1)

    assert _backmerge.main() == 1


def test_a_failed_issue_comment_fails_the_run(monkeypatch) -> None:
    monkeypatch.setattr(_backmerge, "ensure_label", lambda: None)
    monkeypatch.setattr(_backmerge, "open_tracking_issue", lambda: "42")
    monkeypatch.setattr(_backmerge, "already_reported", lambda issue, marker: False)
    monkeypatch.setattr(_backmerge, "mutate", lambda cmd: 1)

    assert not _backmerge.track(
        "abc1234", 2, "branch", ["a.md"], ["abc1234 x"], "url", ""
    )


def test_a_title_edit_failure_does_not_fail_the_run(monkeypatch) -> None:
    # The title only carries the live count. The drift is recorded either way, so
    # a cosmetic failure must not turn the run red.
    monkeypatch.setattr(_backmerge, "ensure_label", lambda: None)
    monkeypatch.setattr(_backmerge, "open_tracking_issue", lambda: "42")
    monkeypatch.setattr(_backmerge, "already_reported", lambda issue, marker: False)
    monkeypatch.setattr(
        _backmerge, "mutate", lambda cmd: 1 if cmd[:3] == ["gh", "issue", "edit"] else 0
    )

    assert _backmerge.track("abc1234", 2, "branch", ["a.md"], ["abc1234 x"], "url", "")


def test_a_failed_push_does_not_claim_the_branch_is_ready(monkeypatch) -> None:
    # A failed push followed by a failed `gh pr create` used to file an issue
    # saying the branch was pushed and ready to propose.
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: None)
    monkeypatch.setattr(_backmerge, "main_only_count", lambda: 2)
    monkeypatch.setattr(_backmerge, "main_head", lambda: "abc1234")
    monkeypatch.setattr(_backmerge, "carried_commits", lambda: ["abc1234 docs: fix"])
    monkeypatch.setattr(_backmerge, "existing_pr", lambda branch: ("", ""))
    monkeypatch.setattr(_backmerge, "remote_branch_exists", lambda branch: False)
    monkeypatch.setattr(_backmerge, "signoff_trailer", lambda: "Signed-off-by: b <b@e>")
    monkeypatch.setattr(_backmerge, "attempt_merge", lambda b, m: [])
    monkeypatch.setattr(_backmerge, "is_ancestry_only", lambda: False)
    monkeypatch.setattr(_backmerge, "mutate", lambda cmd: 1 if "push" in cmd else 0)

    def _explode(*args, **kwargs):
        raise AssertionError("must not propose a branch that never reached the remote")

    monkeypatch.setattr(_backmerge, "open_pr", _explode)

    reasons: list[str] = []
    monkeypatch.setattr(
        _backmerge,
        "track",
        lambda sha, behind, branch, conflicts, commits, url, reason: (
            reasons.append(reason),
            True,
        )[1],
    )

    assert _backmerge.main() == 0
    assert reasons and "pushing the branch failed" in reasons[0]
    assert "pushed and ready" not in reasons[0]


def test_a_clean_merge_pushes_then_opens_the_pull_request(monkeypatch) -> None:
    # The primary happy path: pin the push argv and the ordering.
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: None)
    monkeypatch.setattr(_backmerge, "main_only_count", lambda: 2)
    monkeypatch.setattr(_backmerge, "dco_mismatches", lambda: [])
    monkeypatch.setattr(_backmerge, "main_head", lambda: "abc1234")
    monkeypatch.setattr(_backmerge, "carried_commits", lambda: ["abc1234 docs: fix"])
    monkeypatch.setattr(_backmerge, "existing_pr", lambda branch: ("", ""))
    monkeypatch.setattr(_backmerge, "remote_branch_exists", lambda branch: False)
    monkeypatch.setattr(_backmerge, "signoff_trailer", lambda: "Signed-off-by: b <b@e>")
    monkeypatch.setattr(_backmerge, "attempt_merge", lambda b, m: [])
    monkeypatch.setattr(_backmerge, "is_ancestry_only", lambda: False)
    monkeypatch.setattr(_backmerge, "open_tracking_issue", lambda: "")

    order: list[str] = []
    monkeypatch.setattr(
        _backmerge, "mutate", lambda cmd: (order.append(" ".join(cmd)), 0)[1]
    )
    monkeypatch.setattr(
        _backmerge,
        "open_pr",
        lambda b, c, n, ci, ao=False, dco=None: (order.append(f"open_pr {b}"), 0)[1],
    )

    def _explode(*args, **kwargs):
        raise AssertionError("must not track a successful back-merge")

    monkeypatch.setattr(_backmerge, "track", _explode)

    assert _backmerge.main() == 0
    branch = "rc-dev/chore/back-merge-main-abc1234"
    assert order[0] == f"git push origin {branch}"
    assert order[1] == f"open_pr {branch}"


def test_a_new_pull_request_supersedes_a_stale_tracking_issue(monkeypatch) -> None:
    # An issue filed for an earlier conflicting head otherwise stays open beside
    # the pull request that fixed it, saying the back-merge could not be opened.
    monkeypatch.setattr(_backmerge, "run", lambda cmd, **kw: None)
    monkeypatch.setattr(_backmerge, "main_only_count", lambda: 2)
    monkeypatch.setattr(_backmerge, "dco_mismatches", lambda: [])
    monkeypatch.setattr(_backmerge, "main_head", lambda: "abc1234")
    monkeypatch.setattr(_backmerge, "carried_commits", lambda: ["abc1234 docs: fix"])
    monkeypatch.setattr(_backmerge, "existing_pr", lambda branch: ("", ""))
    monkeypatch.setattr(_backmerge, "remote_branch_exists", lambda branch: False)
    monkeypatch.setattr(_backmerge, "signoff_trailer", lambda: "Signed-off-by: b <b@e>")
    monkeypatch.setattr(_backmerge, "attempt_merge", lambda b, m: [])
    monkeypatch.setattr(_backmerge, "is_ancestry_only", lambda: False)
    monkeypatch.setattr(
        _backmerge, "open_pr", lambda b, c, n, ci, ao=False, dco=None: 0
    )
    monkeypatch.setattr(_backmerge, "open_tracking_issue", lambda: "42")

    closed: list[list[str]] = []
    monkeypatch.setattr(_backmerge, "mutate", lambda cmd: (closed.append(cmd), 0)[1])

    assert _backmerge.main() == 0
    close = [c for c in closed if c[:3] == ["gh", "issue", "close"]]
    assert close and close[0][3] == "42"


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
