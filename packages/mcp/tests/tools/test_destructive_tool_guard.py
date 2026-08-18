"""Tests for the reusable destructive tool confirmation guard."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from _rs_fixtures import authenticated_user, request_with_user

from pipefy_mcp.tools import destructive_tool_guard as guard_mod
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation

RESOURCE = "phase 'Initial' (ID: 42)"
TOOL_NAME = "delete_phase"
IDENTITY = {"phase_id": "42"}


def _assert_approval_before_confirm(message):
    approval_index = message.find("explicit approval")
    confirm_index = message.find("confirm=True")
    assert approval_index != -1
    assert confirm_index != -1
    assert approval_index < confirm_index


def _assert_preview(payload, *, resource=RESOURCE):
    assert payload is not None
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    assert payload["resource"] == resource
    token = payload["confirmation_token"]
    assert isinstance(token, str)
    assert token
    assert token.startswith("v1.")
    assert token in payload["message"]
    assert "cannot be undone" in payload["message"]
    _assert_approval_before_confirm(payload["message"])
    return token


_MISSING_TOKEN_SENTENCE = "The confirmation token is missing."
_INVALID_OR_EXPIRED_TOKEN_SENTENCE = (
    "The previous confirmation token was invalid or expired."
)
_IDENTITY_MISMATCH_TOKEN_SENTENCE = (
    "The previous confirmation token does not match this tool and resource identity."
)


def _assert_missing_token_wording(message):
    assert _MISSING_TOKEN_SENTENCE in message
    assert _INVALID_OR_EXPIRED_TOKEN_SENTENCE not in message
    assert _IDENTITY_MISMATCH_TOKEN_SENTENCE not in message
    assert "confirm=True" in message


def _assert_invalid_or_expired_token_wording(message):
    assert _INVALID_OR_EXPIRED_TOKEN_SENTENCE in message
    assert _MISSING_TOKEN_SENTENCE not in message
    assert _IDENTITY_MISMATCH_TOKEN_SENTENCE not in message
    assert "confirm=True" in message


def _assert_identity_mismatch_token_wording(message):
    assert _IDENTITY_MISMATCH_TOKEN_SENTENCE in message
    assert _MISSING_TOKEN_SENTENCE not in message
    assert _INVALID_OR_EXPIRED_TOKEN_SENTENCE not in message
    assert "expired" not in message.lower()
    assert "confirm=True" in message


def _assert_no_token_status_wording(message):
    """A first look has no earlier token, so it must not report one as faulty."""
    assert _MISSING_TOKEN_SENTENCE not in message
    assert _INVALID_OR_EXPIRED_TOKEN_SENTENCE not in message
    assert _IDENTITY_MISMATCH_TOKEN_SENTENCE not in message


def _make_ctx(*, can_elicit=False, request=None):
    ctx = MagicMock()
    ctx.session.client_params.capabilities.elicitation = can_elicit
    ctx.elicit = AsyncMock()
    if request is not None:
        ctx.request_context.request = request
    return ctx


async def _check(
    ctx,
    *,
    confirm,
    resource_descriptor=RESOURCE,
    resource_identity=IDENTITY,
    tool_name=TOOL_NAME,
    confirmation_token=None,
    dependents_resolver=None,
    irreversible_sentence=None,
):
    return await check_destructive_confirmation(
        ctx,
        confirm=confirm,
        resource_descriptor=resource_descriptor,
        resource_identity=resource_identity,
        tool_name=tool_name,
        confirmation_token=confirmation_token,
        dependents_resolver=dependents_resolver,
        irreversible_sentence=irreversible_sentence,
    )


@pytest.mark.anyio
class TestNoElicitation:
    async def test_no_confirm_returns_preview(self):
        ctx = _make_ctx(can_elicit=False)
        payload = await _check(ctx, confirm=False)
        _assert_preview(payload)
        assert payload["message"].startswith(f"⚠️ Deleting {RESOURCE}")
        ctx.elicit.assert_not_called()

    async def test_custom_irreversible_sentence_is_first_preview_sentence(self):
        ctx = _make_ctx(can_elicit=False)
        sentence = "⚠️ Running this catalog call is permanent and cannot be undone."
        payload = await _check(ctx, confirm=False, irreversible_sentence=sentence)
        _assert_preview(payload)
        assert payload["message"].startswith(sentence)
        ctx.elicit.assert_not_called()

    async def test_first_look_preview_reports_no_token_status(self):
        ctx = _make_ctx(can_elicit=False)
        payload = await _check(ctx, confirm=False)
        _assert_preview(payload)
        _assert_no_token_status_wording(payload["message"])


@pytest.mark.anyio
class TestClientAdvertisesElicitation:
    """Even when the client supports elicitation, only a valid token authorizes deletion."""

    async def test_confirm_false_returns_preview_and_never_elicits(self):
        ctx = _make_ctx(can_elicit=True)
        payload = await _check(ctx, confirm=False)
        _assert_preview(payload)
        ctx.elicit.assert_not_called()


@pytest.mark.anyio
class TestMissingCapabilityMetadata:
    async def test_no_client_params_returns_preview(self):
        ctx = MagicMock()
        ctx.session = SimpleNamespace()
        ctx.elicit = AsyncMock()
        payload = await _check(ctx, confirm=False)
        _assert_preview(payload)
        ctx.elicit.assert_not_called()

    async def test_client_params_without_capabilities_returns_preview(self):
        ctx = MagicMock()
        ctx.session = SimpleNamespace(client_params=SimpleNamespace())
        ctx.elicit = AsyncMock()
        payload = await _check(ctx, confirm=False)
        _assert_preview(payload)
        ctx.elicit.assert_not_called()

    async def test_capabilities_without_elicitation_attr_returns_preview(self):
        ctx = MagicMock()
        ctx.session = SimpleNamespace(
            client_params=SimpleNamespace(capabilities=SimpleNamespace()),
        )
        ctx.elicit = AsyncMock()
        payload = await _check(ctx, confirm=False)
        _assert_preview(payload)
        ctx.elicit.assert_not_called()


@pytest.mark.anyio
class TestTokenAwareConfirmation:
    async def test_confirm_false_with_valid_token_still_previews(self):
        ctx = _make_ctx(can_elicit=False)
        resolver = AsyncMock(return_value={"related": 1})
        first = await _check(ctx, confirm=False, dependents_resolver=resolver)
        token = _assert_preview(first)
        resolver.assert_awaited()

        resolver.reset_mock()
        second = await _check(
            ctx,
            confirm=False,
            confirmation_token=token,
            dependents_resolver=resolver,
        )
        second_token = _assert_preview(second)
        assert second is not None
        assert second_token.startswith("v1.")
        resolver.assert_awaited()
        ctx.elicit.assert_not_called()

    async def test_confirm_true_without_token_previews(self):
        ctx = _make_ctx(can_elicit=True)
        resolver = AsyncMock(return_value={"related": 1})
        payload = await _check(
            ctx,
            confirm=True,
            confirmation_token=None,
            dependents_resolver=resolver,
        )
        _assert_preview(payload)
        _assert_missing_token_wording(payload["message"])
        resolver.assert_awaited()
        ctx.elicit.assert_not_called()

    async def test_confirm_true_with_valid_token_proceeds(self):
        ctx = _make_ctx(can_elicit=False)
        resolver = AsyncMock(return_value={"related": 1})
        preview = await _check(ctx, confirm=False, dependents_resolver=resolver)
        token = _assert_preview(preview)
        resolver.assert_awaited()
        resolver.reset_mock()

        result = await _check(
            ctx,
            confirm=True,
            confirmation_token=token,
            dependents_resolver=resolver,
        )
        assert result is None
        resolver.assert_not_called()
        ctx.elicit.assert_not_called()

    async def test_reworded_descriptor_does_not_invalidate_token(self):
        ctx = _make_ctx(can_elicit=False)
        field_identity = {"field_id": "1"}
        preview = await _check(
            ctx,
            confirm=False,
            resource_descriptor="phase field (ID: 1)",
            resource_identity=field_identity,
        )
        token = _assert_preview(preview, resource="phase field (ID: 1)")

        result = await _check(
            ctx,
            confirm=True,
            resource_descriptor="field 'Priority' (ID: 1)",
            resource_identity=field_identity,
            confirmation_token=token,
        )
        assert result is None

    async def test_wrong_token_previews_with_fresh_token(self):
        ctx = _make_ctx(can_elicit=False)
        payload = await _check(
            ctx,
            confirm=True,
            confirmation_token="not-a-token",
        )
        token = _assert_preview(payload)
        assert token != "not-a-token"
        _assert_invalid_or_expired_token_wording(payload["message"])

    async def test_expired_token_previews_with_fresh_token(self, monkeypatch):
        ctx = _make_ctx(can_elicit=False)
        clock = [1_700_000_000]

        def fake_time():
            return clock[0]

        monkeypatch.setattr(guard_mod.time, "time", fake_time)
        preview = await _check(ctx, confirm=False)
        token = _assert_preview(preview)

        clock[0] += 301
        payload = await _check(ctx, confirm=True, confirmation_token=token)
        fresh = _assert_preview(payload)
        assert payload is not None
        assert fresh != token
        _assert_invalid_or_expired_token_wording(payload["message"])

    async def test_dependents_invoked_on_failed_token_preview(self):
        ctx = _make_ctx(can_elicit=False)
        resolver = AsyncMock(return_value={"related": 1})
        payload = await _check(
            ctx,
            confirm=True,
            confirmation_token="not-a-token",
            dependents_resolver=resolver,
        )
        _assert_preview(payload)
        resolver.assert_awaited()

    async def test_empty_token_previews_as_missing(self):
        ctx = _make_ctx(can_elicit=False)
        payload = await _check(ctx, confirm=True, confirmation_token="")
        _assert_preview(payload)
        _assert_missing_token_wording(payload["message"])

    async def test_identity_mismatch_previews_without_claiming_expiration(self):
        ctx = _make_ctx(can_elicit=False)
        preview = await _check(ctx, confirm=False)
        token = _assert_preview(preview)

        payload = await _check(
            ctx,
            confirm=True,
            resource_identity={"phase_id": "99"},
            confirmation_token=token,
        )
        fresh = _assert_preview(payload)
        assert payload is not None
        assert fresh != token
        _assert_identity_mismatch_token_wording(payload["message"])


@pytest.mark.anyio
class TestHostedBearerDerivedKey:
    async def test_different_bearer_cannot_reuse_token(self):
        ctx_u1 = _make_ctx(
            request=request_with_user(authenticated_user("bearer-u1")),
        )
        preview = await _check(ctx_u1, confirm=False)
        token = _assert_preview(preview)

        ctx_u2 = _make_ctx(
            request=request_with_user(authenticated_user("bearer-u2")),
        )
        stolen = await _check(
            ctx_u2,
            confirm=True,
            confirmation_token=token,
        )
        _assert_preview(stolen)
        assert stolen is not None

    async def test_same_bearer_preview_then_confirm_proceeds(self):
        request = request_with_user(authenticated_user("bearer-u1"))
        ctx = _make_ctx(request=request)
        preview = await _check(ctx, confirm=False)
        token = _assert_preview(preview)

        result = await _check(ctx, confirm=True, confirmation_token=token)
        assert result is None


@pytest.mark.anyio
class TestMissingBearer:
    async def test_missing_bearer_does_not_raise(self):
        ctx = _make_ctx(can_elicit=False)
        payload = await _check(ctx, confirm=False)
        _assert_preview(payload)
        ctx.elicit.assert_not_called()


@pytest.mark.anyio
async def test_signing_key_is_absent_from_preview_and_token_error_envelopes(
    monkeypatch,
):
    canary = b"leak-canary-signing-key-bytes!!"
    monkeypatch.setattr(guard_mod, "signing_key_for", lambda _ctx: canary)
    ctx = _make_ctx(can_elicit=False)

    def assert_key_absent(payload):
        blob = json.dumps(payload, default=str)
        assert canary.decode() not in blob
        assert canary.hex() not in blob
        assert str(canary) not in blob

    preview = await _check(ctx, confirm=False)
    assert_key_absent(preview)

    missing = await _check(ctx, confirm=True, confirmation_token=None)
    assert_key_absent(missing)

    invalid = await _check(ctx, confirm=True, confirmation_token="not-a-token")
    assert_key_absent(invalid)

    mismatch = await _check(
        ctx,
        confirm=True,
        confirmation_token=preview["confirmation_token"],
        resource_identity={"phase_id": "other"},
    )
    assert_key_absent(mismatch)
