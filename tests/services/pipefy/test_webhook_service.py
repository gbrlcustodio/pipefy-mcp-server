"""Unit tests for WebhookService (send inbox email, create/delete webhook)."""

from unittest.mock import AsyncMock

import pytest
from gql.transport.exceptions import TransportQueryError

from pipefy_mcp.services.pipefy.queries.webhook_queries import (
    CREATE_AND_SEND_INBOX_EMAIL_MUTATION,
    CREATE_WEBHOOK_MUTATION,
    DELETE_WEBHOOK_MUTATION,
    GET_CARD_INBOX_EMAILS_QUERY,
    GET_EMAIL_TEMPLATES_QUERY,
    GET_PARSED_EMAIL_TEMPLATE_QUERY,
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
async def test_get_email_templates_success(mock_settings):
    payload = {
        "emailTemplates": {
            "edges": [{"node": {"id": "t1", "name": "Follow-up", "subject": "Hi"}}]
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.get_email_templates("307061640")

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is GET_EMAIL_TEMPLATES_QUERY
    assert variables["repoId"] == 307061640
    assert variables["first"] == 50
    assert result == payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_email_templates_with_filter(mock_settings):
    payload = {"emailTemplates": {"edges": []}}
    service = _make_service(mock_settings, payload)
    await service.get_email_templates("307061640", filter_by_name="Follow", first=10)

    _, variables = service.execute_query.call_args[0]
    assert variables["filterByName"] == "Follow"
    assert variables["first"] == 10


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_parsed_email_template_success(mock_settings):
    payload = {
        "parsedEmailTemplate": {
            "id": "42",
            "subject": "Hello Card",
            "body": "<p>Hi</p>",
            "fromEmail": "s@x.com",
            "toEmail": "r@x.com",
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.get_parsed_email_template(
        "42", card_uuid="550e8400-e29b-41d4-a716-446655440000"
    )

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is GET_PARSED_EMAIL_TEMPLATE_QUERY
    assert variables["emailTemplateId"] == "42"
    assert variables["cardUuid"] == "550e8400-e29b-41d4-a716-446655440000"
    assert result == payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_parsed_email_template_without_card_uuid(mock_settings):
    payload = {"parsedEmailTemplate": {"id": "42", "subject": "Raw"}}
    service = _make_service(mock_settings, payload)
    await service.get_parsed_email_template("42")

    _, variables = service.execute_query.call_args[0]
    assert "cardUuid" not in variables


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
async def test_send_email_with_template_success(mock_settings):
    card_service = AsyncMock()
    card_service.get_card = AsyncMock(
        return_value={
            "card": {
                "uuid": "550e8400-e29b-41d4-a716-446655440000",
                "pipe": {"id": "307061640"},
            }
        }
    )
    service = WebhookService(settings=mock_settings, card_service=card_service)
    service.execute_query = AsyncMock(
        side_effect=[
            {
                "parsedEmailTemplate": {
                    "subject": "Hello",
                    "body": "Body",
                    "fromEmail": "from@x.com",
                    "toEmail": "a@x.com,b@x.com",
                }
            },
            {
                "createAndSendInboxEmail": {
                    "emailSent": True,
                    "errors": [],
                    "inboxEmail": {"id": "e1"},
                }
            },
        ]
    )
    result = await service.send_email_with_template("1320616225", "tmpl-42")

    assert card_service.get_card.await_count == 1
    card_service.get_card.assert_awaited_once_with(1320616225)
    assert service.execute_query.await_count == 2
    first_q, first_vars = service.execute_query.call_args_list[0][0]
    second_q, second_inp = service.execute_query.call_args_list[1][0]
    assert first_q is GET_PARSED_EMAIL_TEMPLATE_QUERY
    assert second_q is CREATE_AND_SEND_INBOX_EMAIL_MUTATION
    assert second_inp["input"]["repoId"] == "307061640"
    assert second_inp["input"]["text"] == "Body"
    assert "html" not in second_inp["input"]
    assert result["createAndSendInboxEmail"]["emailSent"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_email_with_template_rejects_non_numeric_card_id(mock_settings):
    service = WebhookService(settings=mock_settings)
    service.execute_query = AsyncMock()
    with pytest.raises(ValueError, match="numeric card ID"):
        await service.send_email_with_template("not-a-number", "tmpl-1")


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
        pipe_id="601",
        url="https://example.com/hook",
        actions=["card.create"],
    )

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_WEBHOOK_MUTATION
    inp = variables["input"]
    assert inp["pipe_id"] == 601
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
        await service.create_webhook("602", "https://x.com/hook", ["card.move"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_webhook_rejects_http_url(mock_settings):
    service = WebhookService(settings=mock_settings)
    with pytest.raises(ValueError, match="HTTPS"):
        await service.create_webhook("p1", "http://insecure.com/hook", ["card.create"])


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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_card_inbox_emails_success(mock_settings):
    payload = {
        "card": {
            "id": "12345",
            "inbox_emails": [
                {
                    "id": "e1",
                    "type": "sent",
                    "from": "sender@x.com",
                    "fromName": "Sender",
                    "subject": "Hello",
                    "body": "Hi there",
                    "created_at": "2025-01-15T10:00:00Z",
                    "state": "0",
                },
                {
                    "id": "e2",
                    "type": "received",
                    "from": "reply@x.com",
                    "fromName": "Client",
                    "subject": "Re: Hello",
                    "body": "Thanks!",
                    "created_at": "2025-01-15T11:00:00Z",
                    "state": "0",
                },
            ],
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.get_card_inbox_emails("12345")

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is GET_CARD_INBOX_EMAILS_QUERY
    assert variables["card_id"] == 12345
    assert result == payload
    assert len(result["card"]["inbox_emails"]) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_card_inbox_emails_filter_by_sent(mock_settings):
    payload = {
        "card": {
            "id": "12345",
            "inbox_emails": [
                {"id": "e1", "type": "sent", "subject": "Out"},
                {"id": "e2", "type": "received", "subject": "In"},
            ],
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.get_card_inbox_emails("12345", email_type="sent")

    assert result["card"]["inbox_emails"] == [
        {"id": "e1", "type": "sent", "subject": "Out"}
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_card_inbox_emails_filter_by_received(mock_settings):
    payload = {
        "card": {
            "id": "12345",
            "inbox_emails": [
                {"id": "e1", "type": "sent", "subject": "Out"},
                {"id": "e2", "type": "received", "subject": "In"},
            ],
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.get_card_inbox_emails("12345", email_type="received")

    assert result["card"]["inbox_emails"] == [
        {"id": "e2", "type": "received", "subject": "In"}
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_card_inbox_emails_empty_inbox(mock_settings):
    payload = {"card": {"id": "12345", "inbox_emails": []}}
    service = _make_service(mock_settings, payload)
    result = await service.get_card_inbox_emails("12345")

    assert result["card"]["inbox_emails"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_card_inbox_emails_transport_error(mock_settings):
    service = WebhookService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=TransportQueryError("failed", errors=[{"message": "not found"}])
    )
    with pytest.raises(TransportQueryError):
        await service.get_card_inbox_emails("12345")
