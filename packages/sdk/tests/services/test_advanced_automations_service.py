"""Unit tests for AdvancedAutomationsService."""

from __future__ import annotations

import pytest
from _shared.mock_clients import mock_executor

from pipefy_sdk.services.advanced_automations_service import (
    AdvancedAutomationsService,
)


@pytest.mark.anyio
async def test_get_token_returns_token_and_stringifies_pipe_id():
    executor = mock_executor({"advancedAutomationsToken": {"token": "jwt-123"}})
    service = AdvancedAutomationsService(internal_executor=executor)

    token = await service.get_token(303088927)

    assert token == "jwt-123"
    _, variables = executor.execute_query.await_args.args
    assert variables == {"repoId": "303088927"}


@pytest.mark.anyio
async def test_get_token_raises_when_payload_is_empty():
    executor = mock_executor({"advancedAutomationsToken": None})
    service = AdvancedAutomationsService(internal_executor=executor)

    with pytest.raises(ValueError, match="No advanced-automations token"):
        await service.get_token("42")


@pytest.mark.anyio
async def test_get_token_raises_when_token_is_blank():
    executor = mock_executor({"advancedAutomationsToken": {"token": ""}})
    service = AdvancedAutomationsService(internal_executor=executor)

    with pytest.raises(ValueError, match="No advanced-automations token"):
        await service.get_token("42")
