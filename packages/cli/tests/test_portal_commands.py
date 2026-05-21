"""Tests for ``pipefy portal`` read subcommands."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from pipefy_cli.main import app

_PORTAL_LIST_NODE = {
    "uuid": "portal-uuid-1",
    "name": "Main Portal",
    "visibility": "internal",
    "published": True,
}

_PORTAL_DETAIL = {
    "uuid": "portal-uuid-1",
    "name": "Main Portal",
    "visibility": "public",
    "published": True,
    "pages": {
        "nodes": [
            {
                "uuid": "page-1",
                "title": "Home",
                "elements": [
                    {
                        "uuid": "el-1",
                        "type": "forms",
                        "metadata": {"formId": "123"},
                    }
                ],
            }
        ]
    },
    "subPortals": [{"uuid": "sub-1", "name": "Sub Portal 1"}],
}


def test_portal_list_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("portal-list")
    payload = [_PORTAL_LIST_NODE]
    mock_client = MagicMock()
    mock_client.list_portals = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["portal", "list", "--org-uuid", "org-123", "--json"],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == payload
    mock_client.list_portals.assert_awaited_once_with("org-123")


def test_portal_get_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("portal-get")
    mock_client = MagicMock()
    mock_client.get_portal = AsyncMock(return_value=_PORTAL_DETAIL)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["portal", "get", "portal-uuid-1", "--json"],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == _PORTAL_DETAIL
    mock_client.get_portal.assert_awaited_once_with("portal-uuid-1")


def test_portal_list_missing_org_uuid_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-list-missing-org")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["portal", "list", "--json"])
    assert result.exit_code == 2
    mock_client.list_portals.assert_not_called()


def test_portal_get_missing_uuid_exit_2(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("portal-get-missing-uuid")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["portal", "get", "--json"])
    assert result.exit_code == 2
    mock_client.get_portal.assert_not_called()
