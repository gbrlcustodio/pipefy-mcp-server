"""Tests for scripts/release.py pure logic (CHANGELOG stamping, version parsing)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release.py"
_spec = importlib.util.spec_from_file_location("release", _SCRIPT)
assert _spec and _spec.loader
_release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_release)


@pytest.fixture(autouse=True)
def _forbid_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if a test reaches a real ``git``/``uv`` command.

    These tests exercise release *decisions*, not the commands they authorize. A
    guard that stops working would otherwise let a test fall through into a real
    ``bump_version.py`` run, which rewrites every version-bearing file and
    ``uv.lock`` in the working tree — so a broken guard would silently corrupt
    the checkout instead of failing. Tests that need a command stub one
    explicitly; their ``setattr`` wins over this.
    """

    def _forbid(cmd, **kwargs):
        raise AssertionError(f"test reached a real subprocess: {cmd}")

    monkeypatch.setattr(_release, "run", _forbid)
    monkeypatch.setattr(_release, "capture", _forbid)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0.2.0-beta.1", "0.2.0b1"),
        ("0.2.0-alpha.3", "0.2.0a3"),
        ("1.0.0rc2", "1.0.0rc2"),
        ("1.2.3", "1.2.3"),
    ],
)
def test_pep440_normalizes(raw: str, expected: str) -> None:
    assert _release.pep440(raw) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("pipefy, version 0.2.0b1", {"0.2.0b1"}),
        ("pipefy-cli 1.2.3", {"1.2.3"}),
        ("no version here", set()),
        ("0.2.0-beta.1 build", {"0.2.0b1"}),
    ],
)
def test_pep440_candidates(text: str, expected: set[str]) -> None:
    assert _release.pep440_candidates(text) == expected


def test_unreleased_re_captures_heading_and_body() -> None:
    text = (
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "### Added\n- a thing\n\n"
        "## [1.0.0] - 2026-01-01\n\n- old\n"
    )
    m = _release.UNRELEASED_RE.search(text)
    assert m is not None
    assert m.group(1).startswith("## [Unreleased]")
    assert "a thing" in m.group(2)
    assert "old" not in m.group(2)


def test_target_ahead_of_main() -> None:
    assert _release._target_ahead_of_main("0.3.0-beta.2", "0.3.0-beta.1")
    assert _release._target_ahead_of_main("1.0.0", "0.9.0")
    # dev behind main (release bump on main not back-merged): a prerelease bump
    # from dev's alpha lands below main's beta — a downgrade-shaped release.
    assert not _release._target_ahead_of_main("0.3.0-alpha.2", "0.3.0-beta.1")
    # equal is not ahead
    assert not _release._target_ahead_of_main("0.3.0-beta.1", "0.3.0-beta.1")


def test_main_only_commit_count_reads_the_rev_list_range(monkeypatch) -> None:
    # The range must be dev..main: reversed, it would count dev's own work and
    # block every release.
    seen: list[list[str]] = []
    monkeypatch.setattr(_release, "capture", lambda cmd: (seen.append(cmd), "2")[1])
    assert _release._main_only_commit_count() == 2
    assert seen == [["git", "rev-list", "--count", "origin/dev..origin/main"]]


def test_release_pr_body_inlines_content() -> None:
    body = _release._release_pr_body(
        "0.3.0-beta.4", "0.3.0-beta.5", "### Added\n\n- a shipped thing"
    )
    assert "Cuts `v0.3.0-beta.5`" in body
    assert "since `v0.3.0-beta.4`" in body
    assert "`0.3.0-beta.4` -> `0.3.0-beta.5`" in body
    assert "## Released content" in body
    assert "- a shipped thing" in body  # the released notes are inlined
    assert "pre-release PyPI upload" in body
    assert "release.py publish" in body


def test_release_pr_body_marks_stable() -> None:
    body = _release._release_pr_body("0.9.0", "1.0.0", "### Added\n\n- x")
    assert "stable PyPI upload" in body


def test_stamp_changelog_renames_and_reseeds(tmp_path: Path, monkeypatch) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "### Added\n- new feature\n\n"
        "## [1.0.0] - 2026-01-01\n\n- old\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(_release, "CHANGELOG", changelog)

    _release.stamp_changelog("2.0.0")
    out = changelog.read_text(encoding="utf-8")

    # A fresh empty Unreleased is re-seeded above the dated version section.
    assert "## [Unreleased]\n\n## [2.0.0] - " in out
    # The accumulated notes moved under the new version, not lost.
    idx_version = out.index("## [2.0.0]")
    assert "new feature" in out[idx_version:]
    # The prior release section is untouched.
    assert "## [1.0.0] - 2026-01-01" in out


def test_compute_target_version(monkeypatch) -> None:
    monkeypatch.setattr(
        _release.bump_version, "read_sdk_version", lambda: "0.3.0-beta.1"
    )
    assert _release.compute_target_version("major") == ("0.3.0-beta.1", "1.0.0")
    assert _release.compute_target_version("minor") == ("0.3.0-beta.1", "0.4.0")
    assert _release.compute_target_version("patch") == ("0.3.0-beta.1", "0.3.1")
    # prerelease increments the current track; it does not promote alpha->beta.
    assert _release.compute_target_version("prerelease") == (
        "0.3.0-beta.1",
        "0.3.0-beta.2",
    )
    # version= is the escape hatch for a cross-track or arbitrary jump.
    assert _release.compute_target_version("version=0.3.0-rc.1") == (
        "0.3.0-beta.1",
        "0.3.0-rc.1",
    )


def test_newest_run_id_skips_excluded(monkeypatch) -> None:
    # gh lists newest first; the snapshot of prior runs must be skipped so a
    # re-cut of the same tag waits for its genuinely new run.
    monkeypatch.setattr(_release, "_release_run_ids", lambda tag: ["300", "200", "100"])
    assert _release._newest_run_id("v1", frozenset()) == "300"
    assert _release._newest_run_id("v1", frozenset({"300"})) == "200"
    assert _release._newest_run_id("v1", frozenset({"300", "200", "100"})) == ""


def test_compute_target_version_rejects_unknown(monkeypatch) -> None:
    monkeypatch.setattr(_release.bump_version, "read_sdk_version", lambda: "0.3.0")
    with pytest.raises(_release.ReleaseError):
        _release.compute_target_version("bogus")


def test_stamp_changelog_requires_unreleased(tmp_path: Path, monkeypatch) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [1.0.0] - 2026-01-01\n", encoding="utf-8")
    monkeypatch.setattr(_release, "CHANGELOG", changelog)

    with pytest.raises(_release.ReleaseError):
        _release.stamp_changelog("2.0.0")


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        # Alphas are staging cuts; everything else ships from main.
        ("0.5.0-alpha.1", "dev"),
        ("0.5.0a1", "dev"),
        ("0.5.0-beta.1", "main"),
        ("0.5.0-rc.1", "main"),
        ("0.5.0", "main"),
        ("1.0.0", "main"),
    ],
)
def test_release_branch_for_derives_from_track(version: str, expected: str) -> None:
    assert _release.release_branch_for(version) == expected


def test_publish_refuses_an_alpha_from_main(monkeypatch) -> None:
    # publish derives the branch from the version's track, so an alpha checked
    # out on main is refused rather than tagged there.
    monkeypatch.setattr(
        _release.bump_version, "read_sdk_version", lambda: "0.5.0-alpha.1"
    )
    monkeypatch.setattr(_release, "current_branch", lambda: "main")
    with pytest.raises(_release.ReleaseError, match="ships from 'dev'"):
        _release.publish(assume_yes=True)


def test_publish_refuses_a_beta_from_dev(monkeypatch) -> None:
    monkeypatch.setattr(
        _release.bump_version, "read_sdk_version", lambda: "0.5.0-beta.1"
    )
    monkeypatch.setattr(_release, "current_branch", lambda: "dev")
    with pytest.raises(_release.ReleaseError, match="ships from 'main'"):
        _release.publish(assume_yes=True)


def test_beta_bump_is_reachable_through_target_for() -> None:
    # The promotion the dev->main flow needs every cycle must be a named bump,
    # not a hand-typed version= string.
    assert _release.target_for("beta", "0.5.0-alpha.3") == "0.5.0-beta.1"


def test_alpha_target_is_ahead_of_a_released_beta() -> None:
    # The convention's core invariant: the alpha line opens a new X.Y.Z, so it
    # sorts above main's already-released beta rather than below it.
    assert _release._target_ahead_of_main("0.5.0-alpha.1", "0.4.0-beta.2")
    # And an alpha on the same core as that beta does not -- PEP 440 puts
    # 0.4.0a1 below 0.4.0b2, which is why the release flows guard on this.
    assert not _release._target_ahead_of_main("0.4.0-alpha.1", "0.4.0-beta.2")


def test_verify_installer_skips_accepts_a_different_tag(monkeypatch) -> None:
    monkeypatch.setattr(
        _release, "_installer_dry_run", lambda: "Resolved tag: v0.4.0-beta.2\n"
    )
    _release.verify_installer_skips("v0.5.0-alpha.1")


def test_verify_installer_skips_rejects_the_alpha(monkeypatch) -> None:
    # The regression this guards: publishing an alpha repoints the public
    # one-line install at an untested staging build.
    monkeypatch.setattr(
        _release, "_installer_dry_run", lambda: "Resolved tag: v0.5.0-alpha.1\n"
    )
    with pytest.raises(_release.ReleaseError, match="resolved the staging alpha"):
        _release.verify_installer_skips("v0.5.0-alpha.1")


def test_verify_installer_skips_rejects_no_resolution(monkeypatch) -> None:
    monkeypatch.setattr(_release, "_installer_dry_run", lambda: "boom\n")
    with pytest.raises(_release.ReleaseError, match="no resolved tag"):
        _release.verify_installer_skips("v0.5.0-alpha.1")


def test_tag_and_publish_refuses_a_mismatched_checkout(monkeypatch) -> None:
    # The bump commit lands between the caller's preflight and the tag, so the
    # branch is re-asserted here; a stray checkout must not get a tag.
    monkeypatch.setattr(_release, "current_branch", lambda: "main")
    with pytest.raises(_release.ReleaseError, match="must be tagged on 'dev'"):
        _release._tag_and_publish("dev", "0.5.0-alpha.1", assume_yes=True)


def test_tag_and_publish_refuses_a_track_branch_mismatch(monkeypatch) -> None:
    # Even standing on the requested branch, the version's own track decides
    # where it may be tagged -- so a beta can never be tagged on dev.
    monkeypatch.setattr(_release, "current_branch", lambda: "dev")
    with pytest.raises(_release.ReleaseError, match="does not belong on 'dev'"):
        _release._tag_and_publish("dev", "0.5.0-beta.1", assume_yes=True)


@pytest.mark.parametrize(
    "bump",
    ["prerelease", "version=0.5.0-alpha.2", "version=0.6.0-alpha.1", "version=0.5.0a2"],
)
def test_release_pr_refuses_an_alpha_target(bump: str, monkeypatch) -> None:
    # On an alpha line, `prerelease` computes the next alpha. Without this gate
    # release_pr would stamp `## [Unreleased]` into an alpha heading and aim the
    # commit at main -- breaking the contract that only `alpha-pr` cuts alphas.
    monkeypatch.setattr(_release, "working_tree_clean", lambda: True)
    monkeypatch.setattr(_release, "run", lambda *a, **k: None)
    monkeypatch.setattr(_release, "_dev_unreleased_body", lambda: "- a thing")
    monkeypatch.setattr(
        _release,
        "_version_at",
        lambda ref: "0.5.0-alpha.1" if "dev" in ref else "0.4.0-beta.2",
    )
    with pytest.raises(_release.ReleaseError, match="ships from 'dev', not 'main'"):
        _release.release_pr(bump, assume_yes=True)


def test_release_pr_still_allows_the_beta_promotion(monkeypatch) -> None:
    # The gate must not block the promotion the alpha line exists to reach; this
    # fails if _assert_track_ships_from is widened to reject any pre-release.
    monkeypatch.setattr(_release, "working_tree_clean", lambda: True)
    monkeypatch.setattr(_release, "_dev_unreleased_body", lambda: "- a thing")
    monkeypatch.setattr(
        _release,
        "_version_at",
        lambda ref: "0.5.0-alpha.3" if "dev" in ref else "0.4.0-beta.2",
    )
    monkeypatch.setattr(_release, "branch_exists", lambda b: False)
    monkeypatch.setattr(_release, "_main_only_commit_count", lambda: 0)
    calls: list[list[str]] = []
    monkeypatch.setattr(_release, "run", lambda cmd, **k: calls.append(cmd))
    monkeypatch.setattr(_release, "capture", lambda cmd: "https://example/pr/1")
    monkeypatch.setattr(_release, "_apply_prepare", lambda *a, **k: "0.5.0-beta.1")

    _release.release_pr("beta", assume_yes=True)
    assert [
        "git",
        "checkout",
        "-b",
        "rc-main/release/v0.5.0-beta.1",
        "origin/dev",
    ] in calls


@pytest.mark.parametrize("bump", ["version=0.5.0-alpha.1", "version=0.5.0a1"])
def test_prepare_refuses_an_alpha_target(bump: str, monkeypatch) -> None:
    # prepare runs on main; an alpha there would stamp the CHANGELOG and commit
    # an alpha version onto the release branch.
    monkeypatch.setattr(_release, "preflight_prepare", lambda branch: None)
    monkeypatch.setattr(
        _release.bump_version, "read_sdk_version", lambda: "0.4.0-beta.2"
    )
    with pytest.raises(_release.ReleaseError, match="ships from 'dev', not 'main'"):
        _release.prepare(bump, assume_yes=True)


def test_verify_installer_skips_rejects_an_older_alpha(monkeypatch) -> None:
    # A filter that skipped only the newest alpha would leave the installer on an
    # older staging cut -- the same leak, so the check must reject any alpha.
    monkeypatch.setattr(
        _release, "_installer_dry_run", lambda: "Resolved tag: v0.3.0-alpha.1\n"
    )
    with pytest.raises(_release.ReleaseError, match="which is also an alpha"):
        _release.verify_installer_skips("v0.5.0-alpha.1")


def test_verify_installer_skips_rejects_an_unparseable_tag(monkeypatch) -> None:
    monkeypatch.setattr(
        _release, "_installer_dry_run", lambda: "Resolved tag: nightly\n"
    )
    with pytest.raises(_release.ReleaseError, match="not a version tag"):
        _release.verify_installer_skips("v0.5.0-alpha.1")


def _stub_release_pr_env(monkeypatch, dev: str, main: str) -> list[list[str]]:
    """Stub release_pr's surroundings; return the list commands are recorded into."""
    calls: list[list[str]] = []
    monkeypatch.setattr(_release, "working_tree_clean", lambda: True)
    monkeypatch.setattr(_release, "_dev_unreleased_body", lambda: "- a thing")
    monkeypatch.setattr(
        _release, "_version_at", lambda ref: dev if "dev" in ref else main
    )
    monkeypatch.setattr(_release, "branch_exists", lambda b: False)
    monkeypatch.setattr(_release, "_main_only_commit_count", lambda: 0)
    monkeypatch.setattr(_release, "run", lambda cmd, **k: calls.append(cmd))
    monkeypatch.setattr(_release, "capture", lambda cmd: "https://example/pr/1")
    monkeypatch.setattr(_release, "_apply_prepare", lambda bump, target, **k: target)
    return calls


def test_release_pr_refuses_when_main_has_commits_absent_from_dev(monkeypatch) -> None:
    # The version guard passes here (dev's alpha sorts above main's beta), so
    # this is the case only the commit count catches: work merged straight into
    # main without a bump, whose notes the stamped section would omit.
    calls = _stub_release_pr_env(monkeypatch, "0.5.0-alpha.3", "0.4.0-beta.2")
    monkeypatch.setattr(_release, "_main_only_commit_count", lambda: 3)
    with pytest.raises(_release.ReleaseError, match=r"has 3 commit\(s\) not in"):
        _release.release_pr("beta", assume_yes=True)
    # Nothing was created: the operator can walk away at no cost.
    assert not [c for c in calls if c[:3] == ["git", "checkout", "-b"]]
    assert not [c for c in calls if c[:2] == ["git", "push"]]


def test_alpha_pr_refuses_when_main_has_commits_absent_from_dev(monkeypatch) -> None:
    # alpha_pr delegates to release_pr, so the guard covers the staging cut too:
    # an alpha missing what main already shipped does not represent what ships.
    _stub_release_pr_env(monkeypatch, "0.5.0-alpha.3", "0.4.0-beta.2")
    monkeypatch.setattr(_release, "_main_only_commit_count", lambda: 1)
    with pytest.raises(_release.ReleaseError, match=r"has 1 commit\(s\) not in"):
        _release.alpha_pr("prerelease", assume_yes=True)


def test_alpha_pr_targets_dev_and_does_not_stamp(monkeypatch) -> None:
    # dev requires a pull request, so an alpha reaches it the same way a beta
    # reaches main -- and it must not stamp the CHANGELOG on the way.
    calls = _stub_release_pr_env(monkeypatch, "0.4.0-beta.2", "0.4.0-beta.2")
    stamps: list[bool] = []
    monkeypatch.setattr(
        _release,
        "_apply_prepare",
        lambda bump, target, *, stamp=True: (stamps.append(stamp), target)[1],
    )
    _release.alpha_pr("version=0.5.0-alpha.1", assume_yes=True)

    assert stamps == [False], "an alpha must not stamp the CHANGELOG"
    assert [
        "git",
        "checkout",
        "-b",
        "rc-dev/release/v0.5.0-alpha.1",
        "origin/dev",
    ] in calls
    assert ["git", "push", "-u", "origin", "rc-dev/release/v0.5.0-alpha.1"] in calls


def test_release_pr_stamps_for_main(monkeypatch) -> None:
    # The mirror of the above: only a main-bound release finalizes the section.
    _stub_release_pr_env(monkeypatch, "0.5.0-alpha.3", "0.4.0-beta.2")
    stamps: list[bool] = []
    monkeypatch.setattr(
        _release,
        "_apply_prepare",
        lambda bump, target, *, stamp=True: (stamps.append(stamp), target)[1],
    )
    _release.release_pr("beta", assume_yes=True)
    assert stamps == [True]


def test_alpha_pr_refuses_a_non_alpha_target(monkeypatch) -> None:
    _stub_release_pr_env(monkeypatch, "0.5.0-alpha.3", "0.4.0-beta.2")
    with pytest.raises(_release.ReleaseError, match="ships from 'main', not 'dev'"):
        _release.alpha_pr("beta", assume_yes=True)


def _stub_tag_and_publish_env(monkeypatch) -> list[list[str]]:
    """Stub everything around ``_tag_and_publish``; return the recorded commands."""
    calls: list[list[str]] = []
    monkeypatch.setattr(_release, "current_branch", lambda: "dev")
    monkeypatch.setattr(_release, "run", lambda cmd, **k: calls.append(cmd))
    monkeypatch.setattr(_release, "capture", lambda cmd: "samesha")
    monkeypatch.setattr(_release, "tag_exists", lambda t: False)
    monkeypatch.setattr(_release, "local_tag_exists", lambda t: False)
    monkeypatch.setattr(_release, "_release_run_ids", lambda t: [])
    monkeypatch.setattr(_release, "watch_release_workflow", lambda t, **k: None)
    monkeypatch.setattr(_release, "verify", lambda t: None)
    monkeypatch.setattr(_release, "print_release_links", lambda t, v: None)
    return calls


def test_tag_and_publish_never_pushes_the_branch(monkeypatch) -> None:
    # Both release branches reject direct pushes (ruleset requires a PR), so the
    # bump arrives via a merged PR and only the tag is ever pushed. A `git push
    # origin <branch>` here would fail the release outright.
    calls = _stub_tag_and_publish_env(monkeypatch)
    monkeypatch.setattr(_release, "smoke_build_and_install", lambda: None)

    _release._tag_and_publish("dev", "0.5.0-alpha.1", assume_yes=True)

    pushes = [c for c in calls if c[:2] == ["git", "push"]]
    assert pushes == [["git", "push", "origin", "v0.5.0-alpha.1"]]


def test_tag_and_publish_refuses_when_branch_is_not_merged(monkeypatch) -> None:
    # Local ahead of origin means the release PR has not merged, so the commit
    # about to be tagged is not the one on the branch.
    monkeypatch.setattr(_release, "current_branch", lambda: "dev")
    monkeypatch.setattr(_release, "run", lambda cmd, **k: None)
    shas = iter(["localsha", "remotesha"])
    monkeypatch.setattr(_release, "capture", lambda cmd: next(shas))
    with pytest.raises(_release.ReleaseError, match="Merge the release PR"):
        _release._tag_and_publish("dev", "0.5.0-alpha.1", assume_yes=True)


@pytest.mark.parametrize(
    ("bump", "current"),
    [
        # An unpromotable track and an unparseable explicit version both come back
        # from bump_version as ValueError; the CLI must report them as release
        # errors, not tracebacks. `release-pr beta` on a beta line is the case
        # that actually happens.
        ("beta", "0.4.0-beta.2"),
        ("prerelease", "0.2.0-dev.1"),
        ("version=not-a-version", "0.4.0-beta.2"),
    ],
)
def test_target_for_reports_bump_rejections_as_release_errors(
    bump: str, current: str
) -> None:
    with pytest.raises(_release.ReleaseError):
        _release.target_for(bump, current)


# --- the pre-publish artifact check ----------------------------------------


def test_expected_wheel_stems_are_derived_from_the_published_members() -> None:
    # The wheel set every release must attach is derived, not typed out again:
    # adding a published member updates it with no edit here. The literals pin
    # the escaping -- a wheel filename replaces the dashes a name carries.
    assert set(_release.EXPECTED_WHEEL_STEMS) == {
        "pipefy-",
        "pipefy_auth-",
        "pipefy_cli-",
        "pipefy_infra-",
        "pipefy_mcp_server-",
    }
    assert len(_release.EXPECTED_WHEEL_STEMS) == len(
        _release.smoke_entry_points.PUBLISHED_DISTRIBUTIONS
    )


def test_tag_and_publish_checks_the_artifacts_before_tagging(monkeypatch) -> None:
    # The whole point of the check: it runs on the reversible side, so a wheel
    # that cannot start costs nothing instead of a tag and a GitHub Release.
    calls = _stub_tag_and_publish_env(monkeypatch)
    monkeypatch.setattr(
        _release, "smoke_build_and_install", lambda: calls.append(["<smoke>"])
    )

    _release._tag_and_publish("dev", "0.5.0-alpha.1", assume_yes=True)

    smoke = calls.index(["<smoke>"])
    assert smoke < calls.index(["git", "tag", "v0.5.0-alpha.1"])
    assert smoke < calls.index(["git", "push", "origin", "v0.5.0-alpha.1"])


def test_tag_and_publish_aborts_when_the_artifacts_fail(monkeypatch) -> None:
    calls = _stub_tag_and_publish_env(monkeypatch)

    def _boom() -> None:
        raise _release.ReleaseError("wheels do not launch")

    monkeypatch.setattr(_release, "smoke_build_and_install", _boom)
    with pytest.raises(_release.ReleaseError, match="wheels do not launch"):
        _release._tag_and_publish("dev", "0.5.0-alpha.1", assume_yes=True)

    # Nothing irreversible happened, which is what makes the failure free.
    assert not [c for c in calls if c[:2] == ["git", "tag"]]
    assert not [c for c in calls if c[:2] == ["git", "push"]]


def test_tag_and_publish_checks_repo_state_before_building(monkeypatch) -> None:
    # A colliding tag or a stray checkout must fail in a second, not after a
    # two-minute build, so the cheap guards stay ahead of the check.
    _stub_tag_and_publish_env(monkeypatch)
    monkeypatch.setattr(_release, "tag_exists", lambda t: True)
    monkeypatch.setattr(
        _release,
        "smoke_build_and_install",
        lambda: pytest.fail("built the wheels before the repository-state guards"),
    )
    with pytest.raises(_release.ReleaseError, match="already exists on origin"):
        _release._tag_and_publish("dev", "0.5.0-alpha.1", assume_yes=True)


def test_the_confirmation_states_the_artifacts_passed(monkeypatch) -> None:
    # The prompt carries what the check found, so the operator confirming the
    # irreversible push is told the wheels start rather than having to remember.
    _stub_tag_and_publish_env(monkeypatch)
    monkeypatch.setattr(_release, "smoke_build_and_install", lambda: None)
    prompts: list[str] = []
    monkeypatch.setattr(_release, "confirm", lambda prompt, **k: prompts.append(prompt))

    _release._tag_and_publish("dev", "0.5.0-alpha.1", assume_yes=True)

    assert len(prompts) == 1
    assert "install and launch" in prompts[0]


def test_smoke_build_and_install_runs_the_shared_script_from_a_temp_dir(
    monkeypatch,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(_release, "run", lambda cmd, **k: calls.append(cmd))
    monkeypatch.setattr(
        _release.smoke_entry_points,
        "check_wheels",
        lambda directory: ["pipefy-1.0-py3-none-any.whl"],
    )

    _release.smoke_build_and_install()

    build = calls[0]
    assert build[:5] == ["uv", "build", "--all-packages", "--wheel", "-o"]
    out_dir = Path(build[5])
    # Never dist/: a stale local build must not be mistaken for this one, and the
    # check leaves nothing behind.
    assert out_dir.name == "dist"
    assert not out_dir.is_relative_to(_release.REPO_ROOT)
    # The temp tree is gone once the check returns.
    assert not out_dir.parent.exists()

    # The launch half is the same script every workflow runs, under the fresh
    # virtualenv's interpreter -- not this process's.
    launch = calls[-1]
    assert launch[1] == str(_release.SMOKE_SCRIPT)
    assert launch[0] != _release.sys.executable
    installed = calls[-2]
    assert installed[:4] == [launch[0], "-m", "pip", "install"]
    assert installed[4].endswith("pipefy-1.0-py3-none-any.whl")


def test_smoke_build_and_install_reports_an_incomplete_wheel_set(monkeypatch) -> None:
    # The build produced nothing here, which is exactly what check_wheels exists
    # to catch: pip would satisfy the absent members from the index.
    monkeypatch.setattr(_release, "run", lambda cmd, **k: None)
    with pytest.raises(_release.ReleaseError, match="has no wheel for"):
        _release.smoke_build_and_install()


def test_smoke_run_names_the_step_and_says_nothing_shipped(monkeypatch) -> None:
    def _fail(cmd, **kwargs):
        raise _release.subprocess.CalledProcessError(2, cmd)

    monkeypatch.setattr(_release, "run", _fail)
    with pytest.raises(_release.ReleaseError) as exc:
        _release._smoke_run("install the built wheels", ["pip", "install", "x"])
    assert "install the built wheels" in str(exc.value)
    assert "Nothing was tagged" in str(exc.value)


def test_apply_prepare_signs_off_the_release_commit(monkeypatch) -> None:
    # A Signed-off-by trailer lives inside the message, so an unsigned release
    # commit is repaired only by an amend and a force-push on the open release
    # pull request. #635 needed exactly that.
    calls: list[list[str]] = []
    monkeypatch.setattr(_release, "run", lambda cmd, **k: calls.append(cmd))
    monkeypatch.setattr(
        _release.bump_version, "read_sdk_version", lambda: "0.5.0-beta.1"
    )
    monkeypatch.setattr(_release, "stamp_changelog", lambda v: None)

    _release._apply_prepare("beta", "0.5.0-beta.1")

    [commit] = [c for c in calls if c[:2] == ["git", "commit"]]
    assert "-s" in commit, commit
