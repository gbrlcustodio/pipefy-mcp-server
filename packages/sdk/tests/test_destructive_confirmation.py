"""Contract tests for minting and verifying HMAC confirmation tokens."""

import base64
import hashlib
import hmac
import json
from unittest.mock import MagicMock

import pytest

from pipefy_sdk.destructive_confirmation import (
    DESTRUCTIVE_CONFIRMATION_TTL_SECONDS,
    classify_confirmation_token_failure,
    confirmation_signing_key,
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


def test_spliced_payload_and_mac_from_same_key_fails():
    identity_b = {"field_id": "2", "pipe_uuid": "abc"}
    token_a = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity=IDENTITY,
        key=KEY,
        now=NOW,
    )
    token_b = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity=identity_b,
        key=KEY,
        now=NOW,
    )
    _, payload_a, _ = token_a.split(".")
    _, _, mac_b = token_b.split(".")
    spliced = f"v1.{payload_a}.{mac_b}"
    assert (
        verify_confirmation_token(
            spliced,
            tool_name=TOOL,
            resource_identity=IDENTITY,
            key=KEY,
            now=NOW + 1,
        )
        is False
    )
    assert (
        verify_confirmation_token(
            spliced,
            tool_name=TOOL,
            resource_identity=identity_b,
            key=KEY,
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


def test_whitespace_in_token_part_fails():
    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity=IDENTITY,
        key=KEY,
        now=NOW,
    )
    version, payload_b64, mac_b64 = token.split(".")
    spaced = f"{version}.{payload_b64} .{mac_b64}"
    assert (
        verify_confirmation_token(
            spaced,
            tool_name=TOOL,
            resource_identity=IDENTITY,
            key=KEY,
            now=NOW + 1,
        )
        is False
    )


def test_standard_base64_alphabet_in_token_part_fails():
    # Non-ASCII identity so the payload segment carries base64url "-" or "_";
    # swapping those for the standard "+" and "/" decodes to identical bytes,
    # so only an alphabet check rejects it.
    identity = {"pipe_id": "çãé~ÿþ"}
    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity=identity,
        key=KEY,
        now=NOW,
    )
    version, payload_b64, mac_b64 = token.split(".")
    assert "-" in payload_b64 or "_" in payload_b64
    standard = f"{version}.{payload_b64.replace('-', '+').replace('_', '/')}.{mac_b64}"
    assert standard != token
    assert (
        verify_confirmation_token(
            standard,
            tool_name=TOOL,
            resource_identity=identity,
            key=KEY,
            now=NOW + 1,
        )
        is False
    )
    assert (
        verify_confirmation_token(
            token,
            tool_name=TOOL,
            resource_identity=identity,
            key=KEY,
            now=NOW + 1,
        )
        is True
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
    expected_mac = hmac.new(KEY, b"v1." + payload_raw, hashlib.sha256).digest()
    assert hmac.compare_digest(mac_raw, expected_mac)
    payload_only_mac = hmac.new(KEY, payload_raw, hashlib.sha256).digest()
    assert not hmac.compare_digest(mac_raw, payload_only_mac)


def test_mint_stringifies_non_json_identity_values():
    class NotJson:
        def __str__(self):
            return "not-json"

    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity={"field_id": NotJson()},
        key=KEY,
        now=NOW,
    )
    assert token.startswith("v1.")
    payload = json.loads(_b64url_decode(token.split(".")[1]))
    assert payload["identity"]["field_id"] == "not-json"


def test_non_json_identity_value_round_trips_to_verify():
    """A stringified identity must still verify, or the caller previews forever."""

    class NotJson:
        def __str__(self):
            return "not-json"

    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity={"field_id": NotJson()},
        key=KEY,
        now=NOW,
    )
    assert (
        verify_confirmation_token(
            token,
            tool_name=TOOL,
            resource_identity={"field_id": NotJson()},
            key=KEY,
            now=NOW + 1,
        )
        is True
    )


def test_old_format_token_signed_over_payload_only_is_rejected():
    """A token whose MAC omits the version prefix predates the version binding."""
    payload_bytes = json.dumps(
        {"exp": NOW + 300, "identity": IDENTITY, "tool": TOOL},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    legacy_mac = hmac.new(KEY, payload_bytes, hashlib.sha256).digest()
    legacy_token = (
        "v1."
        + base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode("ascii")
        + "."
        + base64.urlsafe_b64encode(legacy_mac).rstrip(b"=").decode("ascii")
    )

    assert (
        verify_confirmation_token(
            legacy_token,
            tool_name=TOOL,
            resource_identity=IDENTITY,
            key=KEY,
            now=NOW + 1,
        )
        is False
    )


@pytest.mark.parametrize("token", [None, ""])
def test_classify_reports_missing_for_absent_token(token):
    assert (
        classify_confirmation_token_failure(
            token,
            tool_name=TOOL,
            resource_identity=IDENTITY,
            key=KEY,
        )
        == "missing"
    )


def test_classify_reports_invalid_for_a_token_signed_with_another_key():
    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity=IDENTITY,
        key=OTHER_KEY,
        now=NOW,
    )

    assert (
        classify_confirmation_token_failure(
            token,
            tool_name=TOOL,
            resource_identity=IDENTITY,
            key=KEY,
        )
        == "invalid_or_expired"
    )


def test_classify_reports_identity_mismatch_for_another_tool():
    token = mint_confirmation_token(
        tool_name="delete_label",
        resource_identity=IDENTITY,
        key=KEY,
        now=NOW,
    )

    assert (
        classify_confirmation_token_failure(
            token,
            tool_name=TOOL,
            resource_identity=IDENTITY,
            key=KEY,
        )
        == "identity_mismatch"
    )


def test_classify_reports_identity_mismatch_for_another_resource():
    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity={"field_id": "99", "pipe_uuid": "abc"},
        key=KEY,
        now=NOW,
    )

    assert (
        classify_confirmation_token_failure(
            token,
            tool_name=TOOL,
            resource_identity=IDENTITY,
            key=KEY,
        )
        == "identity_mismatch"
    )


def test_tampered_version_prefix_is_rejected():
    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity=IDENTITY,
        key=KEY,
        now=NOW,
    )
    tampered = "v2." + token.split(".", 1)[1]

    assert (
        verify_confirmation_token(
            tampered,
            tool_name=TOOL,
            resource_identity=IDENTITY,
            key=KEY,
            now=NOW + 1,
        )
        is False
    )


def test_verify_uses_hmac_compare_digest(monkeypatch):
    import hmac as hmac_mod

    from pipefy_sdk import destructive_confirmation as planner

    spy = MagicMock(wraps=hmac_mod.compare_digest)
    monkeypatch.setattr(planner.hmac, "compare_digest", spy)

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

    from pipefy_sdk import destructive_confirmation as planner

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


def test_helpers_are_exported_from_the_package_root():
    import pipefy_sdk
    from pipefy_sdk import destructive_confirmation as planner

    for name in (
        "DESTRUCTIVE_CONFIRMATION_TTL_SECONDS",
        "ConfirmationTokenFailure",
        "classify_confirmation_token_failure",
        "confirmation_signing_key",
        "mint_confirmation_token",
        "verify_confirmation_token",
    ):
        assert name in pipefy_sdk.__all__
        assert getattr(pipefy_sdk, name) is getattr(planner, name)


def test_wire_format_matches_the_pinned_vector():
    """Pin the token bytes so a mint and a verify on different builds agree.

    Verification derives its key from the caller, not from server state, so a
    rolling deploy has one build mint and another verify. Changing the payload
    layout, the MAC message, or the base64 spelling breaks that pair mid-deploy.
    """
    assert (
        mint_confirmation_token(
            tool_name=TOOL,
            resource_identity=IDENTITY,
            key=KEY,
            now=NOW,
        )
        == "v1.eyJleHAiOjE3MDAwMDAzMDAsImlkZW50aXR5Ijp7ImZpZWxkX2lkIjoiMSIsInBpcGVfdXVpZCI6ImFiYyJ9LCJ0b29sIjoiZGVsZXRlX3BoYXNlX2ZpZWxkIn0"
        ".SO7bsGv4zk4uNJLxdn6dYJihtYV2ybCysDaLq8U8PoE"
    )


def test_signing_key_is_sha256_of_the_utf8_credential():
    bearer = "caller-a-bearer"

    assert (
        confirmation_signing_key(bearer)
        == hashlib.sha256(bearer.encode("utf-8")).digest()
    )
    assert confirmation_signing_key(bearer) == confirmation_signing_key(
        bearer.encode("utf-8")
    )


def test_each_caller_gets_a_distinct_key():
    """One caller's token must not confirm another caller's deletion.

    ``test_wrong_key_fails`` pins the half that rejects a foreign key. This pins
    the half that hands two callers two different keys in the first place.
    """
    assert confirmation_signing_key("caller-a") != confirmation_signing_key("caller-b")


def test_signing_key_does_not_leak_the_credential():
    bearer = "caller-a-bearer"
    key = confirmation_signing_key(bearer)

    assert bearer.encode("utf-8") not in key
    token = mint_confirmation_token(
        tool_name=TOOL,
        resource_identity=IDENTITY,
        key=key,
        now=NOW,
    )
    assert bearer not in token
