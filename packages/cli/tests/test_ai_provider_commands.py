"""Tests for ``pipefy ai-provider`` commands."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from pipefy_cli.main import app

BYOM_NODE = {
    "__typename": "LlmProvider",
    "id": "42",
    "name": "Azure custom",
    "type": "byom",
    "active": True,
    "organizationDefault": False,
    "configuration": {"auth": {"accessToken": "__REDACTED__"}},
}

SYSTEM_NODE = {
    "__typename": "SystemLlmProvider",
    "id": "7",
    "name": "Pipefy GPT",
    "type": "system",
    "organizationDefault": True,
    "systemDefault": True,
    "state": "active",
    "configuration": {"model": "gpt-4o"},
}


def _env(monkeypatch) -> None:
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "sec")


def _client_patch(mock_client):
    return patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    )


def test_ai_provider_list_json(runner, clean_pipefy_env, saved_cwd, monkeypatch):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.get_llm_providers = AsyncMock(
        return_value={
            "providers": [SYSTEM_NODE, BYOM_NODE],
            "page_info": {"hasNextPage": False, "endCursor": None},
        }
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "ai-provider",
                "list",
                "--org-uuid",
                "org-uuid-1",
                "--only-active",
                "--first",
                "10",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    data = json.loads(result.stdout)
    assert data["success"] is True
    assert [p["type"] for p in data["providers"]] == ["system", "byom"]
    mock_client.get_llm_providers.assert_awaited_once_with(
        "org-uuid-1", only_active=True, first=10, after=None
    )


def test_ai_provider_models_json(runner, clean_pipefy_env, saved_cwd, monkeypatch):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.get_available_ai_models = AsyncMock(return_value=["gpt-4o"])

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            ["ai-provider", "models", "--provider-name", "openai", "--json"],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == {"success": True, "models": ["gpt-4o"]}
    mock_client.get_available_ai_models.assert_awaited_once_with("openai")


def test_ai_provider_default_get_defaults_owner_type(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.get_default_llm_provider = AsyncMock(return_value=BYOM_NODE)

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            ["ai-provider", "default", "get", "--owner-id", "123456", "--json"],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    data = json.loads(result.stdout)
    assert data["provider"]["id"] == "42"
    mock_client.get_default_llm_provider.assert_awaited_once_with(
        "123456", owner_type="organization"
    )


def test_ai_provider_dependencies_json(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.get_llm_provider_dependencies = AsyncMock(
        return_value={
            "dependencies": [{"ownerId": "1", "ownerType": "organization"}],
            "page_info": {"hasNextPage": False, "endCursor": None},
            "total_count": 1,
        }
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "ai-provider",
                "dependencies",
                "--provider-id",
                "42",
                "--org-uuid",
                "org-uuid-1",
                "--after",
                "cur-1",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    data = json.loads(result.stdout)
    assert data["total_count"] == 1
    mock_client.get_llm_provider_dependencies.assert_awaited_once_with(
        "42", "org-uuid-1", first=50, after="cur-1"
    )


def test_ai_provider_validate_access_green_exits_0(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_llm_provider_access = AsyncMock(
        return_value={
            "ok": True,
            "system_providers_visible": True,
            "custom_providers_visible": True,
            "provider_count": 2,
            "note": "Read access confirmed.",
        }
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            ["ai-provider", "validate-access", "--org-uuid", "org-uuid-1", "--json"],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    data = json.loads(result.stdout)
    assert data["success"] is True
    assert data["ok"] is True


def test_ai_provider_validate_access_failure_exits_1_with_problem(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_llm_provider_access = AsyncMock(
        return_value={
            "ok": False,
            "problem": {
                "kind": "permission_denied",
                "message": "Permission denied",
                "code": "PERMISSION_DENIED",
                "correlation_id": None,
            },
        }
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            ["ai-provider", "validate-access", "--org-uuid", "org-uuid-1", "--json"],
        )
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["success"] is False
    assert data["problem"]["kind"] == "permission_denied"


def test_ai_provider_list_blank_org_uuid_exits_2(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()

    async def raise_value_error(*args, **kwargs):
        raise ValueError("organization_uuid must be a non-empty string")

    mock_client.get_llm_providers = AsyncMock(side_effect=raise_value_error)

    with _client_patch(mock_client):
        result = runner.invoke(
            app, ["ai-provider", "list", "--org-uuid", "  ", "--json"]
        )
    assert result.exit_code == 2
    assert "organization_uuid" in (result.stderr or "")
