"""Contract tests for the destructive confirmation token planner (REQ-1)."""

import base64
import json
from unittest.mock import MagicMock

import pytest

from pipefy_mcp.tools.destructive_confirmation_token import (
    DESTRUCTIVE_CONFIRMATION_TTL_SECONDS,
    mint_confirmation_token,
    verify_confirmation_token,
)

KEY = b"\x01" * 32
OTHER_KEY = b"\x02" * 32
NOW = 1_700_000_000
TOOL = "delete_phase_field"
IDENTITY = {"field_id": "1", "pipe_uuid": "abc"}


def _b64url_decode(part):
    padding = "=" * ((4 - len(part) % 4) % 4)
    return base64.urlsafe_b64decode(part + padding)


def test_ttl_constant_is_300():
    assert DESTRUCTIVE_CONFIRMATION_TTL_SECONDS == 300


def test_mint_then_verify_same_key_succeeds():
    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity=IDENTITY,
        key=KEY,
        now=NOW,
    )
    assert (
        verify_confirmation_token(
            token,
            tool_name=TOOL,
            resource_identity=IDENTITY,
            key=KEY,
            now=NOW + 1,
        )
        is True
    )


def test_identity_key_order_does_not_matter():
    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity={"field_id": "1", "pipe_uuid": "abc"},
        key=KEY,
        now=NOW,
    )
    assert (
        verify_confirmation_token(
            token,
            tool_name=TOOL,
            resource_identity={"pipe_uuid": "abc", "field_id": "1"},
            key=KEY,
            now=NOW + 1,
        )
        is True
    )


def test_int_and_str_ids_are_equivalent():
    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity={"field_id": 1},
        key=KEY,
        now=NOW,
    )
    assert (
        verify_confirmation_token(
            token,
            tool_name=TOOL,
            resource_identity={"field_id": "1"},
            key=KEY,
            now=NOW + 1,
        )
        is True
    )


def test_list_order_does_not_matter():
    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity={"user_ids": ["2", "1"]},
        key=KEY,
        now=NOW,
    )
    assert (
        verify_confirmation_token(
            token,
            tool_name=TOOL,
            resource_identity={"user_ids": ["1", "2"]},
            key=KEY,
            now=NOW + 1,
        )
        is True
    )


def test_wrong_key_fails():
    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity=IDENTITY,
        key=KEY,
        now=NOW,
    )
    assert (
        verify_confirmation_token(
            token,
            tool_name=TOOL,
            resource_identity=IDENTITY,
            key=OTHER_KEY,
            now=NOW + 1,
        )
        is False
    )


def test_tool_mismatch_fails():
    token = mint_confirmation_token(
        tool_name="delete_phase_field",
        resource_identity=IDENTITY,
        key=KEY,
        now=NOW,
    )
    assert (
        verify_confirmation_token(
            token,
            tool_name="delete_pipe",
            resource_identity=IDENTITY,
            key=KEY,
            now=NOW + 1,
        )
        is False
    )


def test_identity_mismatch_fails():
    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity={"field_id": "1", "table_id": "10"},
        key=KEY,
        now=NOW,
    )
    assert (
        verify_confirmation_token(
            token,
            tool_name=TOOL,
            resource_identity={"field_id": "1", "table_id": "11"},
            key=KEY,
            now=NOW + 1,
        )
        is False
    )


def test_dropped_identity_key_is_not_a_wildcard():
    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity={"field_id": "prioridade", "pipe_uuid": "A"},
        key=KEY,
        now=NOW,
    )
    assert (
        verify_confirmation_token(
            token,
            tool_name=TOOL,
            resource_identity={"field_id": "prioridade"},
            key=KEY,
            now=NOW + 1,
        )
        is False
    )


def test_token_expires_at_ttl_boundary():
    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity=IDENTITY,
        key=KEY,
        now=NOW,
    )
    ttl = DESTRUCTIVE_CONFIRMATION_TTL_SECONDS
    assert ttl == 300
    assert (
        verify_confirmation_token(
            token,
            tool_name=TOOL,
            resource_identity=IDENTITY,
            key=KEY,
            now=NOW + ttl - 1,
        )
        is True
    )
    assert (
        verify_confirmation_token(
            token,
            tool_name=TOOL,
            resource_identity=IDENTITY,
            key=KEY,
            now=NOW + ttl,
        )
        is False
    )
    assert (
        verify_confirmation_token(
            token,
            tool_name=TOOL,
            resource_identity=IDENTITY,
            key=KEY,
            now=NOW + ttl + 1,
        )
        is False
    )


@pytest.mark.parametrize("token", ["not-a-token", "", None])
def test_garbage_or_none_token_returns_false(token):
    assert (
        verify_confirmation_token(
            token,
            tool_name=TOOL,
            resource_identity=IDENTITY,
            key=KEY,
            now=NOW,
        )
        is False
    )


def test_minted_token_wire_format():
    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity=IDENTITY,
        key=KEY,
        now=NOW,
    )
    assert token.startswith("v1.")
    parts = token.split(".")
    assert len(parts) == 3
    version, payload_b64, mac_b64 = parts
    assert version == "v1"
    payload_raw = _b64url_decode(payload_b64)
    mac_raw = _b64url_decode(mac_b64)
    assert payload_raw
    assert mac_raw
    json.loads(payload_raw)


def test_verify_uses_hmac_compare_digest(monkeypatch):
    import hmac as hmac_mod

    from pipefy_mcp.tools import destructive_confirmation_token as planner

    spy = MagicMock(wraps=hmac_mod.compare_digest)
    if hasattr(planner, "hmac"):
        monkeypatch.setattr(planner.hmac, "compare_digest", spy)
    else:
        monkeypatch.setattr(planner, "compare_digest", spy)

    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity=IDENTITY,
        key=KEY,
        now=NOW,
    )
    assert (
        verify_confirmation_token(
            token,
            tool_name=TOOL,
            resource_identity=IDENTITY,
            key=KEY,
            now=NOW + 1,
        )
        is True
    )
    spy.assert_called()


def test_planner_has_no_io():
    import inspect

    from pipefy_mcp.tools import destructive_confirmation_token as planner

    source = inspect.getsource(planner)
    assert "Context" not in source
    assert "PipefyClient" not in source
    assert "os.environ" not in source


def test_token_payload_does_not_contain_key_and_has_canonical_fields():
    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity=IDENTITY,
        key=KEY,
        now=NOW,
    )
    payload_raw = _b64url_decode(token.split(".")[1])
    payload = json.loads(payload_raw)
    assert list(payload.keys()) == ["exp", "identity", "tool"]
    assert isinstance(payload["identity"], dict)
    assert not isinstance(payload["identity"], str)
    assert "key" not in payload
    assert KEY not in payload_raw
    assert KEY.decode("latin-1") not in token
    assert payload["tool"] == TOOL
    assert payload["exp"] == NOW + DESTRUCTIVE_CONFIRMATION_TTL_SECONDS
