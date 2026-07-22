"""Tests for ``pipefy service-account`` subcommands."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from pipefy_cli.main import app

ORG = "341c1327-261c-4766-bb96-7953e4c3970d"


def test_service_account_create_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("sa-create")
    mock_client = MagicMock()
    mock_client.create_service_account = AsyncMock(
        return_value={"createServiceAccount": {"serviceAccount": {"id": "1"}}}
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "service-account",
                "create",
                "--org",
                ORG,
                "--name",
                "ci-bot",
                "--role",
                "normal",
                "--json",
            ],
        )
    assert result.exit_code == 0
    mock_client.create_service_account.assert_awaited_once_with(
        organization_uuid=ORG,
        name="ci-bot",
        role="normal",
        description=None,
        expiration=None,
        pipe_ids=None,
        pipe_role="admin",
    )


def test_service_account_create_with_pipe_ids(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("sa-create-pipes")
    mock_client = MagicMock()
    mock_client.create_service_account = AsyncMock(
        return_value={"createServiceAccount": {"serviceAccount": {}}}
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "service-account",
                "create",
                "--org",
                ORG,
                "--name",
                "ci-bot",
                "--pipe-ids",
                "10,20",
                "--json",
            ],
        )
    assert result.exit_code == 0
    mock_client.create_service_account.assert_awaited_once_with(
        organization_uuid=ORG,
        name="ci-bot",
        role="normal",
        description=None,
        expiration=None,
        pipe_ids=["10", "20"],
        pipe_role="admin",
    )


def test_service_account_create_with_expiration(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("sa-create-exp")
    mock_client = MagicMock()
    mock_client.create_service_account = AsyncMock(
        return_value={"createServiceAccount": {"serviceAccount": {}}}
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "service-account",
                "create",
                "--org",
                ORG,
                "--name",
                "ci-bot",
                "--expiration-unit",
                "days",
                "--expiration-value",
                "1",
                "--json",
            ],
        )
    assert result.exit_code == 0
    mock_client.create_service_account.assert_awaited_once_with(
        organization_uuid=ORG,
        name="ci-bot",
        role="normal",
        description=None,
        expiration={"unit": "days", "value": 1},
        pipe_ids=None,
        pipe_role="admin",
    )


def test_service_account_create_long_name_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("sa-create-long")
    mock_client = MagicMock()
    mock_client.create_service_account = AsyncMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["service-account", "create", "--org", ORG, "--name", "x" * 21],
        )
    assert result.exit_code == 2
    mock_client.create_service_account.assert_not_called()


def test_service_account_create_half_expiration_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("sa-create-halfexp")
    mock_client = MagicMock()
    mock_client.create_service_account = AsyncMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "service-account",
                "create",
                "--org",
                ORG,
                "--name",
                "ci-bot",
                "--expiration-unit",
                "days",
            ],
        )
    assert result.exit_code == 2
    mock_client.create_service_account.assert_not_called()


def test_service_account_delete_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("sa-delete")
    mock_client = MagicMock()
    mock_client.delete_service_account = AsyncMock(
        return_value={"deleteServiceAccount": {"success": True}}
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "service-account",
                "delete",
                "--org",
                ORG,
                "--id",
                "sa-uuid-1",
                "--yes",
                "--json",
            ],
        )
    assert result.exit_code == 0
    mock_client.delete_service_account.assert_awaited_once_with(
        organization_uuid=ORG, service_account_uuid="sa-uuid-1"
    )
