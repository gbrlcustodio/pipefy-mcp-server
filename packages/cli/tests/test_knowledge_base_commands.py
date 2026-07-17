"""Tests for ``pipefy kb`` knowledge base commands."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from pipefy_cli.main import app

PLAIN_TEXT_NODE = {
    "id": "kb-1",
    "type": "knowledge_base_plain_texts",
    "name": "Onboarding",
    "description": "How to onboard",
    "updatedAt": "2026-07-17T00:00:00Z",
}

PLAIN_TEXT_FULL = {
    "id": "kb-1",
    "name": "Onboarding",
    "description": "How to onboard",
    "content": "Step 1...",
    "updatedAt": "2026-07-17T00:00:00Z",
}

GREEN_PROBE = {"ok": True, "knowledge_base_count": 1, "note": "Read access confirmed."}
DENIED_PROBE = {
    "ok": False,
    "problem": {
        "kind": "permission_denied",
        "message": "Permission denied",
        "code": "PERMISSION_DENIED",
    },
}


def _env(monkeypatch) -> None:
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "sec")


def _client_patch(mock_client):
    return patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    )


def test_kb_list_json(runner, clean_pipefy_env, saved_cwd, monkeypatch):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.get_ai_knowledge_bases = AsyncMock(return_value=[PLAIN_TEXT_NODE])

    with _client_patch(mock_client):
        result = runner.invoke(
            app, ["kb", "list", "--pipe-uuid", "pipe-uuid-1", "--json"]
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    data = json.loads(result.stdout)
    assert data["success"] is True
    assert data["knowledge_bases"] == [PLAIN_TEXT_NODE]
    mock_client.get_ai_knowledge_bases.assert_awaited_once_with("pipe-uuid-1")


def test_kb_validate_access_green_exits_0(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_knowledge_base_access = AsyncMock(return_value=GREEN_PROBE)

    with _client_patch(mock_client):
        result = runner.invoke(
            app, ["kb", "validate-access", "--pipe-uuid", "pipe-uuid-1", "--json"]
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout)["success"] is True


def test_kb_validate_access_failure_exits_1(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_knowledge_base_access = AsyncMock(return_value=DENIED_PROBE)

    with _client_patch(mock_client):
        result = runner.invoke(
            app, ["kb", "validate-access", "--pipe-uuid", "pipe-uuid-1", "--json"]
        )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["success"] is False


def test_kb_plain_text_get_json(runner, clean_pipefy_env, saved_cwd, monkeypatch):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.get_ai_knowledge_base_plain_text = AsyncMock(
        return_value=PLAIN_TEXT_FULL
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "plain-text",
                "get",
                "--id",
                "kb-1",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout)["knowledge_base_plain_text"] == PLAIN_TEXT_FULL
    mock_client.get_ai_knowledge_base_plain_text.assert_awaited_once_with(
        "kb-1", "pipe-uuid-1"
    )


def test_kb_plain_text_create_gated_on_probe(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_knowledge_base_access = AsyncMock(return_value=GREEN_PROBE)
    mock_client.create_ai_knowledge_base_plain_text = AsyncMock(
        return_value=PLAIN_TEXT_FULL
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "plain-text",
                "create",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--name",
                "Onboarding",
                "--content",
                "Step 1...",
                "--description",
                "How to onboard",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout)["success"] is True
    mock_client.create_ai_knowledge_base_plain_text.assert_awaited_once_with(
        "pipe-uuid-1",
        name="Onboarding",
        content="Step 1...",
        description="How to onboard",
    )


def test_kb_plain_text_create_denied_probe_blocks_write(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_knowledge_base_access = AsyncMock(return_value=DENIED_PROBE)
    mock_client.create_ai_knowledge_base_plain_text = AsyncMock()

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "plain-text",
                "create",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--name",
                "n",
                "--content",
                "c",
                "--description",
                "d",
                "--json",
            ],
        )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["success"] is False
    mock_client.create_ai_knowledge_base_plain_text.assert_not_awaited()


def test_kb_plain_text_update_partial(runner, clean_pipefy_env, saved_cwd, monkeypatch):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.validate_knowledge_base_access = AsyncMock(return_value=GREEN_PROBE)
    mock_client.update_ai_knowledge_base_plain_text = AsyncMock(
        return_value=PLAIN_TEXT_FULL
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "plain-text",
                "update",
                "--id",
                "kb-1",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--content",
                "New content",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    mock_client.update_ai_knowledge_base_plain_text.assert_awaited_once_with(
        "kb-1", "pipe-uuid-1", name=None, content="New content", description=None
    )


def test_kb_plain_text_delete_with_yes(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.delete_ai_knowledge_base_plain_text = AsyncMock(
        return_value={"success": True, "errors": []}
    )

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "plain-text",
                "delete",
                "--id",
                "kb-1",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--yes",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout)["success"] is True
    mock_client.delete_ai_knowledge_base_plain_text.assert_awaited_once_with(
        "kb-1", "pipe-uuid-1"
    )


def test_kb_plain_text_delete_aborts_without_confirmation(
    runner, clean_pipefy_env, saved_cwd, monkeypatch
):
    _env(monkeypatch)
    mock_client = MagicMock()
    mock_client.delete_ai_knowledge_base_plain_text = AsyncMock()

    with _client_patch(mock_client):
        result = runner.invoke(
            app,
            [
                "kb",
                "plain-text",
                "delete",
                "--id",
                "kb-1",
                "--pipe-uuid",
                "pipe-uuid-1",
                "--json",
            ],
            input="n\n",
        )
    assert result.exit_code != 0
    mock_client.delete_ai_knowledge_base_plain_text.assert_not_awaited()
