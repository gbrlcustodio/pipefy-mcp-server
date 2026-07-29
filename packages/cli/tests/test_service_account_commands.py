"""Tests for ``pipefy service-account`` subcommands."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipefy_cli.main import app

ORG = "341c1327-261c-4766-bb96-7953e4c3970d"
SECRET = "csecret"

# Every field the gates read is non-null in the schema, so a realistic payload
# always carries ``success`` and a client secret.
CREATED = {
    "createServiceAccount": {
        "success": True,
        "serviceAccount": {
            "id": "1",
            "uuid": "sa-uuid-1",
            "email": "sa@x.com",
            "client": {"id": "cid", "secret": SECRET},
            "token": {"endpoint": "https://token"},
        },
    }
}


def test_service_account_create_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("sa-create")
    mock_client = MagicMock()
    mock_client.create_service_account = AsyncMock(return_value=CREATED)
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
    # Printing the secret once is the command's purpose.
    assert SECRET in result.stdout
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
    mock_client.create_service_account = AsyncMock(return_value=CREATED)
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
    mock_client.create_service_account = AsyncMock(return_value=CREATED)
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


def _invoke_create(runner, mock_client, *, json_out: bool = True):
    args = ["service-account", "create", "--org", ORG, "--name", "ci-bot"]
    if json_out:
        args.append("--json")
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        return runner.invoke(app, args)


def _invoke_delete(runner, mock_client):
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        return runner.invoke(
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


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param({"createServiceAccount": None}, id="null-mutation-node"),
        pytest.param({}, id="missing-mutation-node"),
        pytest.param(
            {
                "createServiceAccount": {
                    "success": False,
                    "serviceAccount": {
                        "uuid": "sa-uuid-1",
                        "client": {"secret": SECRET},
                    },
                }
            },
            id="soft-failure-with-secret",
        ),
    ],
)
def test_service_account_create_soft_failure_exits_1(
    runner, clean_pipefy_env, saved_cwd, oauth_env, raw
):
    """The API's own success flag decides, even when a secret rode along."""
    oauth_env("sa-create-soft")
    mock_client = MagicMock()
    mock_client.create_service_account = AsyncMock(return_value=raw)
    result = _invoke_create(runner, mock_client)
    assert result.exit_code == 1
    assert "did not succeed" in result.stdout
    assert SECRET not in result.stdout
    assert SECRET not in result.stderr


@pytest.mark.parametrize(
    "account",
    [
        pytest.param(None, id="null-account"),
        pytest.param({"uuid": "sa-uuid-1", "client": None}, id="null-client"),
        pytest.param(
            {"uuid": "sa-uuid-1", "client": {"secret": None}}, id="null-secret"
        ),
        pytest.param(
            {"uuid": "sa-uuid-1", "client": {"secret": ""}}, id="empty-secret"
        ),
    ],
)
def test_service_account_create_without_secret_exits_1(
    runner, clean_pipefy_env, saved_cwd, oauth_env, account
):
    """A reported success with no usable one-shot secret is still a failure."""
    oauth_env("sa-create-nosecret")
    mock_client = MagicMock()
    mock_client.create_service_account = AsyncMock(
        return_value={
            "createServiceAccount": {"success": True, "serviceAccount": account}
        }
    )
    result = _invoke_create(runner, mock_client)
    assert result.exit_code == 1
    assert "no client secret" in result.stdout


def test_service_account_create_without_secret_surfaces_uuid_for_cleanup(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    """The account may exist unreachable, so the caller needs its uuid to delete it."""
    oauth_env("sa-create-nosecret-uuid")
    mock_client = MagicMock()
    mock_client.create_service_account = AsyncMock(
        return_value={
            "createServiceAccount": {
                "success": True,
                "serviceAccount": {"uuid": "sa-uuid-1", "client": None},
            }
        }
    )
    result = _invoke_create(runner, mock_client)
    assert result.exit_code == 1
    assert "sa-uuid-1" in result.stdout


def test_service_account_create_soft_failure_rich_output_hides_secret(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    """The default (non-JSON) rendering must not leak the secret either."""
    oauth_env("sa-create-soft-rich")
    mock_client = MagicMock()
    mock_client.create_service_account = AsyncMock(
        return_value={
            "createServiceAccount": {
                "success": False,
                "serviceAccount": {"client": {"secret": SECRET}},
            }
        }
    )
    result = _invoke_create(runner, mock_client, json_out=False)
    assert result.exit_code == 1
    assert SECRET not in result.stdout
    assert SECRET not in result.stderr


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param({"deleteServiceAccount": {"success": False}}, id="success-false"),
        pytest.param({"deleteServiceAccount": None}, id="null-node"),
        pytest.param({}, id="missing-node"),
    ],
)
def test_service_account_delete_soft_failure_exits_1(
    runner, clean_pipefy_env, saved_cwd, oauth_env, raw
):
    oauth_env("sa-delete-soft")
    mock_client = MagicMock()
    mock_client.delete_service_account = AsyncMock(return_value=raw)
    result = _invoke_delete(runner, mock_client)
    assert result.exit_code == 1
    assert "did not succeed" in result.stdout
