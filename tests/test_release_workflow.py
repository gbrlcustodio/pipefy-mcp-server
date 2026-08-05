"""Release workflow drift guard: nothing publishes before the artifacts are checked.

The step order *is* the contract. A smoke install that runs after ``Create GitHub
Release`` leaves a published Release advertising wheels that cannot start, and
withdrawing one is manual work. The workflow states that boundary in a comment;
a comment is documentation, so the ordering is asserted here as well.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RELEASE_YML = _REPO_ROOT / ".github" / "workflows" / "release.yml"

_SMOKE_STEP = "Smoke install staged wheels (clean venv)"
_PUBLISH_STEPS = ("Create GitHub Release", "Upload to PyPI")


def _step_index(workflow: str, name: str) -> int:
    """Line index of the ``- name: <name>`` step, or fail naming the missing step."""
    for index, line in enumerate(workflow.splitlines()):
        if line.strip() == f"- name: {name}":
            return index
    raise AssertionError(
        f"release.yml has no step named {name!r}. If it was renamed, update this "
        "guard; the ordering it protects still has to hold."
    )


def test_no_step_publishes_before_the_smoke_install() -> None:
    workflow = _RELEASE_YML.read_text(encoding="utf-8")
    smoke = _step_index(workflow, _SMOKE_STEP)
    for name in _PUBLISH_STEPS:
        assert _step_index(workflow, name) > smoke, (
            f"{name!r} runs before {_SMOKE_STEP!r}. A failing install would then "
            "leave a published artifact behind, which is the defect the "
            "validate-then-publish band exists to prevent."
        )


def test_no_step_opts_out_of_fail_fast() -> None:
    # Ordering alone is not enough: `continue-on-error` on any step in the validate
    # band lets the publish steps run after a failed check, which is the same defect
    # by another route.
    workflow = _RELEASE_YML.read_text(encoding="utf-8")
    assert "continue-on-error" not in workflow, (
        "A step in release.yml opts out of fail-fast, so a failed check no longer "
        "stops the publish steps."
    )
