"""Tests for enrich_permission_denied_error helper."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError

from pipefy_mcp.services.pipefy import PipefyClient
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
    return client


@pytest.mark.anyio
class TestEnrichPermissionDeniedError:
    async def test_permission_denied_missing_member_returns_enrichment(
        self, mock_client
    ):
        exc = _make_permission_denied_exc()
        # Fetching members for the target pipe fails (no access)
        mock_client.get_pipe_members.side_effect = [
            # Source pipe — accessible
            {"pipe": {"name": "Source Pipe", "members": [{"user": {"id": "u1"}}]}},
            # Target pipe — raises (no access)
            RuntimeError("no access to pipe"),
        ]
        result = await enrich_permission_denied_error(exc, ["100", "200"], mock_client)
        assert result is not None
        assert "pipe 200" in result
        assert "invite_members" in result

    async def test_permission_denied_is_member_returns_none(self, mock_client):
        exc = _make_permission_denied_exc()
        mock_client.get_pipe_members.return_value = {
            "pipe": {
                "name": "Pipe",
                "members": [{"user": {"id": "u1"}, "role_name": "admin"}],
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
                "members": [{"user": {"id": "u1"}}],
            }
        }
        await enrich_permission_denied_error(exc, ["100", "100"], mock_client)
        # Should only call once despite duplicate IDs
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
