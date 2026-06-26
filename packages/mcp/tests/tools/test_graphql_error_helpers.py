"""Tests for enrich_permission_denied_error helper.

The enrichment keys on the acting (authenticated) caller identity resolved via
``get_me``: the failed call was made as that identity, so its own membership is
what the message should reflect.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from pipefy_sdk import PipefyClient

import pipefy_mcp.settings as settings_mod
from pipefy_mcp.tools.graphql_error_helpers import enrich_permission_denied_error


def _make_permission_denied_exc(message="forbidden"):
    return TransportQueryError(
        message,
        errors=[
            {
                "message": message,
                "extensions": {"code": "PERMISSION_DENIED"},
            }
        ],
    )


def _make_non_permission_exc(message="not found"):
    return TransportQueryError(
        message,
        errors=[
            {
                "message": message,
                "extensions": {"code": "NOT_FOUND"},
            }
        ],
    )


@pytest.fixture
def mock_client():
    client = MagicMock(spec=PipefyClient)
    client.get_pipe_members = AsyncMock()
    # Default acting identity; tests vary membership by aligning member ids with
    # this id (or override get_me to return a different id / None / raise).
    client.get_me = AsyncMock(
        return_value={"id": "caller", "email": "c@example.com", "name": "Caller"}
    )
    return client


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    mock_settings = MagicMock()
    mock_settings.mcp.permission_denied_enrichment_timeout_seconds = 5.0
    monkeypatch.setattr(settings_mod, "settings", mock_settings)


@pytest.mark.anyio
class TestEnrichPermissionDeniedError:
    async def test_permission_denied_unverifiable_pipe_returns_enrichment(
        self, mock_client
    ):
        exc = _make_permission_denied_exc()
        mock_client.get_pipe_members.side_effect = [
            # Source pipe -- accessible, caller is a member.
            {"pipe": {"name": "Source Pipe", "members": [{"user": {"id": "caller"}}]}},
            # Target pipe -- raises (no access).
            RuntimeError("no access to pipe"),
        ]
        result = await enrich_permission_denied_error(exc, ["100", "200"], mock_client)
        assert result is not None
        assert "pipe 200" in result
        assert "invite_members" in result
        # The message is softened for the unverifiable case.
        assert "Could not verify your membership" in result

    async def test_permission_denied_caller_is_member_returns_none(self, mock_client):
        exc = _make_permission_denied_exc()
        mock_client.get_pipe_members.return_value = {
            "pipe": {
                "name": "Pipe",
                "members": [{"user": {"id": "caller"}, "role_name": "admin"}],
            }
        }
        result = await enrich_permission_denied_error(exc, ["100", "200"], mock_client)
        assert result is None

    async def test_non_permission_denied_returns_none(self, mock_client):
        exc = _make_non_permission_exc()
        result = await enrich_permission_denied_error(exc, ["100"], mock_client)
        assert result is None
        mock_client.get_pipe_members.assert_not_called()

    async def test_timeout_returns_none(self, mock_client):
        import asyncio

        exc = _make_permission_denied_exc()

        async def slow_fetch(*args, **kwargs):
            await asyncio.sleep(10)
            return {}

        mock_client.get_pipe_members.side_effect = slow_fetch
        result = await enrich_permission_denied_error(exc, ["100"], mock_client)
        assert result is None

    async def test_uses_configured_enrichment_timeout(self, mock_client, monkeypatch):
        """Waits for ``settings.mcp.permission_denied_enrichment_timeout_seconds``."""
        import asyncio

        mock_settings = MagicMock()
        mock_settings.mcp.permission_denied_enrichment_timeout_seconds = 0.1
        monkeypatch.setattr(settings_mod, "settings", mock_settings)

        exc = _make_permission_denied_exc()

        async def slow_fetch(*args, **kwargs):
            await asyncio.sleep(1.0)
            return {"pipe": {"members": []}}

        mock_client.get_pipe_members.side_effect = slow_fetch
        result = await enrich_permission_denied_error(exc, ["100"], mock_client)
        assert result is None

    async def test_empty_pipe_ids_returns_none(self, mock_client):
        exc = _make_permission_denied_exc()
        result = await enrich_permission_denied_error(exc, [], mock_client)
        assert result is None
        mock_client.get_pipe_members.assert_not_called()

    async def test_deduplicates_pipe_ids(self, mock_client):
        exc = _make_permission_denied_exc()
        mock_client.get_pipe_members.return_value = {
            "pipe": {
                "name": "Pipe",
                "members": [{"user": {"id": "caller"}}],
            }
        }
        await enrich_permission_denied_error(exc, ["100", "100"], mock_client)
        # Should only call once despite duplicate IDs.
        assert mock_client.get_pipe_members.call_count == 1

    async def test_empty_members_list_reports_missing(self, mock_client):
        exc = _make_permission_denied_exc()
        mock_client.get_pipe_members.return_value = {
            "pipe": {"name": "Target Pipe", "members": []}
        }
        result = await enrich_permission_denied_error(exc, ["100"], mock_client)
        assert result is not None
        assert "Target Pipe" in result
        assert "invite_members" in result

    async def test_caller_not_in_members_returns_enrichment(self, mock_client):
        """A non-empty members list that excludes the caller is still flagged."""
        exc = _make_permission_denied_exc()
        mock_client.get_pipe_members.return_value = {
            "pipe": {
                "name": "Target Pipe",
                "members": [
                    {"user": {"id": "other-user-1"}, "role_name": "admin"},
                    {"user": {"id": "other-user-2"}, "role_name": "member"},
                ],
            }
        }
        result = await enrich_permission_denied_error(exc, ["200"], mock_client)
        assert result is not None
        assert "Target Pipe" in result
        assert "You are not a member" in result
        assert "invite_members" in result

    async def test_caller_is_member_returns_none(self, mock_client):
        """No false positive when the caller is among the members."""
        exc = _make_permission_denied_exc()
        mock_client.get_pipe_members.return_value = {
            "pipe": {
                "name": "Target Pipe",
                "members": [
                    {"user": {"id": "caller"}, "role_name": "admin"},
                    {"user": {"id": "other-user"}, "role_name": "member"},
                ],
            }
        }
        result = await enrich_permission_denied_error(exc, ["200"], mock_client)
        assert result is None

    async def test_unresolved_caller_skips_membership_check(self, mock_client):
        """When get_me cannot resolve the caller, a non-empty members list is left alone.

        Without a caller id the membership comparison is impossible, so the
        enrichment degrades gracefully (only the empty-members case is reported).
        """
        exc = _make_permission_denied_exc()
        mock_client.get_me = AsyncMock(return_value=None)
        mock_client.get_pipe_members.return_value = {
            "pipe": {
                "name": "Target Pipe",
                "members": [{"user": {"id": "u1"}, "role_name": "admin"}],
            }
        }
        result = await enrich_permission_denied_error(exc, ["200"], mock_client)
        assert result is None

    async def test_get_me_failure_does_not_break_enrichment(self, mock_client):
        """A get_me error degrades to the unresolved-caller path, not a raise."""
        exc = _make_permission_denied_exc()
        mock_client.get_me = AsyncMock(side_effect=RuntimeError("me lookup failed"))
        mock_client.get_pipe_members.return_value = {
            "pipe": {"name": "Target Pipe", "members": []}
        }
        result = await enrich_permission_denied_error(exc, ["200"], mock_client)
        # Empty members still flagged; the get_me failure is swallowed.
        assert result is not None
        assert "Target Pipe" in result
