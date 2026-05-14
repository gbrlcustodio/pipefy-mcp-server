"""Unit tests for service-account removal policy helpers."""

from __future__ import annotations

from pipefy_sdk.services.member_service import (
    format_service_account_removal_block_message,
    service_account_removal_blocked_user_ids,
)


def test_blocked_user_ids_empty_when_no_protected() -> None:
    assert service_account_removal_blocked_user_ids(["a", "b"], []) == []


def test_blocked_user_ids_matches_protected() -> None:
    out = service_account_removal_blocked_user_ids(
        ["x", "svc", "y"],
        ["svc"],
    )
    assert out == ["svc"]


def test_format_block_message_singular() -> None:
    msg = format_service_account_removal_block_message(["one"])
    assert "Cannot remove service account one" in msg


def test_format_block_message_plural() -> None:
    msg = format_service_account_removal_block_message(["a", "b"])
    assert "Cannot remove service accounts a, b" in msg
