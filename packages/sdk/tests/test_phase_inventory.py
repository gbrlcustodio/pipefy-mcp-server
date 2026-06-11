from __future__ import annotations

import pytest

from pipefy_sdk.phase_inventory import (
    get_phase_not_found_message,
    is_get_phase_not_found_error,
)


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("phase.cards_count missing from response"),
        ValueError("phase id missing from response"),
    ],
)
def test_is_get_phase_not_found_error_matches_sdk_value_errors(exc: ValueError) -> None:
    assert is_get_phase_not_found_error(exc) is True


def test_is_get_phase_not_found_error_rejects_other_value_errors() -> None:
    assert is_get_phase_not_found_error(ValueError("other")) is False


def test_is_get_phase_not_found_error_rejects_non_value_errors() -> None:
    assert (
        is_get_phase_not_found_error(RuntimeError("phase.cards_count missing")) is False
    )


def test_get_phase_not_found_message() -> None:
    assert get_phase_not_found_message(99) == "Phase 99 not found or access denied."
