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


# --- Write commands ------------------------------------------------------

WRITTEN_PROVIDER = {
    "id": "42",
    "name": "My OpenAI",
    "type": "byom",
    "active": True,
    "organizationDefault": False,
}


def _green_probe() -> dict:
    return {"ok": True, "system_providers_visible": True, "provider_count": 1}


def _config_file(tmp_path) -> str:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"provider": "openai", "auth": {"token": "sk-PLACE"}}))
    return str(path)


def test_ai_provider_create_probe_gated_success(
    runner, clean_pipefy_env, saved_cwd, monkeypatch, tmp_path
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_llm_provider_access = AsyncMock(return_value=_green_probe())
    mock_client.create_llm_provider = AsyncMock(return_value=WRITTEN_PROVIDER)
    cfg = _config_file(tmp_path)

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "ai-provider",
                "create",
                "--org-uuid",
                "org-uuid-1",
                "--name",
                "My OpenAI",
                "--config-file",
                cfg,
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    data = json.loads(result.stdout)
    assert data["provider"]["id"] == "42"
    assert "configuration" not in json.dumps(data)  # secret never returned
    call = mock_client.create_llm_provider.await_args
    assert call.args == ("org-uuid-1",)
    assert call.kwargs["name"] == "My OpenAI"
    assert str(call.kwargs["configuration_file_path"]) == cfg


def test_ai_provider_create_blocked_by_partial_denial_probe(
    runner, clean_pipefy_env, saved_cwd, monkeypatch, tmp_path
):
    """A probe that is ok BUT carries a problem is partial denial: write blocked."""
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_llm_provider_access = AsyncMock(
        return_value={
            "ok": True,
            "provider_count": 1,
            "problem": {"kind": "permission_denied", "message": "Partial denial"},
        }
    )
    mock_client.create_llm_provider = AsyncMock()

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "ai-provider",
                "create",
                "--org-uuid",
                "org-uuid-1",
                "--name",
                "X",
                "--config-file",
                _config_file(tmp_path),
                "--json",
            ],
        )
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["success"] is False
    assert data["problem"]["kind"] == "permission_denied"
    mock_client.create_llm_provider.assert_not_awaited()


def test_ai_provider_update_probe_gated_success(
    runner, clean_pipefy_env, saved_cwd, monkeypatch, tmp_path
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_llm_provider_access = AsyncMock(return_value=_green_probe())
    mock_client.update_llm_provider = AsyncMock(return_value=WRITTEN_PROVIDER)
    cfg = _config_file(tmp_path)

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "ai-provider",
                "update",
                "--id",
                "42",
                "--org-uuid",
                "org-uuid-1",
                "--config-file",
                cfg,
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    call = mock_client.update_llm_provider.await_args
    assert call.args == ("42", "org-uuid-1")
    assert str(call.kwargs["configuration_file_path"]) == cfg
    assert call.kwargs["name"] is None


def test_ai_provider_delete_requires_confirmation_abort(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.delete_llm_provider = AsyncMock()

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            ["ai-provider", "delete", "--id", "42", "--org-uuid", "org-uuid-1"],
            input="n\n",
        )
    assert result.exit_code != 0
    mock_client.delete_llm_provider.assert_not_awaited()


def test_ai_provider_delete_yes_executes(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.delete_llm_provider = AsyncMock(return_value={"success": True})

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "ai-provider",
                "delete",
                "--id",
                "42",
                "--org-uuid",
                "org-uuid-1",
                "--yes",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    mock_client.delete_llm_provider.assert_awaited_once_with("42", "org-uuid-1")


def test_ai_provider_set_active_status_inactive(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.set_llm_provider_active_status = AsyncMock(
        return_value={"success": True}
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            ["ai-provider", "set-active-status", "--id", "42", "--inactive", "--json"],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    data = json.loads(result.stdout)
    assert data == {"success": True, "provider_id": "42", "active": False}
    mock_client.set_llm_provider_active_status.assert_awaited_once_with(
        "42", active=False
    )


def test_ai_provider_default_set_provider_id(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.set_default_llm_provider = AsyncMock(
        return_value={"id": "a1", "llmProviderId": "42"}
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "ai-provider",
                "default",
                "set",
                "--org-id",
                "123456",
                "--provider-id",
                "42",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    mock_client.set_default_llm_provider.assert_awaited_once_with(
        "123456", provider_id="42", system_provider_id=None
    )


def test_ai_provider_default_set_xor_violation_exits_2(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()

    async def raise_value_error(*args, **kwargs):
        raise ValueError("Provide exactly one of provider_id or system_provider_id.")

    mock_client.set_default_llm_provider = AsyncMock(side_effect=raise_value_error)

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "ai-provider",
                "default",
                "set",
                "--org-id",
                "123456",
                "--provider-id",
                "42",
                "--system-provider-id",
                "7",
                "--json",
            ],
        )
    assert result.exit_code == 2
    assert "exactly one" in (result.stderr or "")


def test_ai_provider_default_reset(runner, clean_pipefy_env, saved_cwd, monkeypatch):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.reset_default_llm_provider = AsyncMock(return_value={"success": True})

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            ["ai-provider", "default", "reset", "--org-id", "123456", "--json"],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    data = json.loads(result.stdout)
    assert data == {"success": True, "organization_id": "123456"}
    mock_client.reset_default_llm_provider.assert_awaited_once_with("123456")
