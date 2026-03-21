"""Unit tests for WebhookService (send inbox email, create/delete webhook)."""

from unittest.mock import AsyncMock

import pytest
from gql.transport.exceptions import TransportQueryError

from pipefy_mcp.services.pipefy.queries.webhook_queries import (
    CREATE_AND_SEND_INBOX_EMAIL_MUTATION,
    CREATE_WEBHOOK_MUTATION,
    DELETE_WEBHOOK_MUTATION,
)
from pipefy_mcp.services.pipefy.webhook_service import WebhookService
from pipefy_mcp.settings import PipefySettings


@pytest.fixture
def mock_settings():
    return PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret="client_secret",
    )


def _make_service(mock_settings, return_value: dict):
    service = WebhookService(settings=mock_settings)
    service.execute_query = AsyncMock(return_value=return_value)
    return service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_inbox_email_success(mock_settings):
    payload = {
        "createAndSendInboxEmail": {
            "emailSent": True,
            "errors": [],
            "inboxEmail": {"id": "e1"},
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.send_inbox_email(
        card_id="card-1",
        to=["a@x.com"],
        subject="Hello",
        body="Hi there",
        from_="sender@pipefy.com",
    )

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_AND_SEND_INBOX_EMAIL_MUTATION
    inp = variables["input"]
    assert inp["cardId"] == "card-1"
    assert inp["to"] == ["a@x.com"]
    assert inp["subject"] == "Hello"
    assert inp["from"] == "sender@pipefy.com"
    assert inp["text"] == "Hi there"
    assert result == payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_inbox_email_transport_error(mock_settings):
    service = WebhookService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "denied"}])
    )
    with pytest.raises(TransportQueryError):
        await service.send_inbox_email(
            "c1", ["x@y.com"], "Subj", "Body", from_="s@x.com"
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_webhook_success(mock_settings):
    payload = {
        "createWebhook": {
            "webhook": {
                "id": "w1",
                "url": "https://example.com/hook",
                "actions": ["card.create"],
            }
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.create_webhook(
        pipe_id="pipe-1",
        url="https://example.com/hook",
        actions=["card.create"],
    )

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_WEBHOOK_MUTATION
    inp = variables["input"]
    assert inp["pipe_id"] == "pipe-1"
    assert inp["url"] == "https://example.com/hook"
    assert inp["actions"] == ["card.create"]
    assert result == payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_webhook_transport_error(mock_settings):
    service = WebhookService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "bad"}])
    )
    with pytest.raises(TransportQueryError):
        await service.create_webhook(
            "p1", "https://x.com/hook", ["card.move"]
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_webhook_rejects_http_url(mock_settings):
    service = WebhookService(settings=mock_settings)
    with pytest.raises(ValueError, match="HTTPS"):
        await service.create_webhook(
            "p1", "http://insecure.com/hook", ["card.create"]
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_webhook_success(mock_settings):
    payload = {"deleteWebhook": {"success": True}}
    service = _make_service(mock_settings, payload)
    result = await service.delete_webhook("webhook-1")

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is DELETE_WEBHOOK_MUTATION
    assert variables["input"] == {"id": "webhook-1"}
    assert result == payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_webhook_transport_error(mock_settings):
    service = WebhookService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "gone"}])
    )
    with pytest.raises(TransportQueryError):
        await service.delete_webhook("w1")
