"""Tests for email and webhook MCP tools (mocked PipefyClient)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from gql.transport.exceptions import TransportQueryError
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import (
    create_connected_server_and_client_session as create_client_session,
)

from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.tools.webhook_tools import WebhookTools


@pytest.fixture
def mock_webhook_client():
    client = MagicMock(PipefyClient)
    client.get_email_templates = AsyncMock()
    client.send_inbox_email = AsyncMock()
    client.send_email_with_template = AsyncMock()
    client.get_card_inbox_emails = AsyncMock()
    client.create_webhook = AsyncMock()
    client.get_webhooks = AsyncMock()
    client.update_webhook = AsyncMock()
    client.delete_webhook = AsyncMock()
    return client


@pytest.fixture
def webhook_mcp_server(mock_webhook_client):
    mcp = FastMCP("Webhook Tools Test")
    WebhookTools.register(mcp, mock_webhook_client)
    return mcp


@pytest.fixture
def webhook_session(webhook_mcp_server, request):
    elicitation = getattr(request, "param", None)
    return create_client_session(
        webhook_mcp_server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
        elicitation_callback=elicitation,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_send_inbox_email_success(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.send_inbox_email.return_value = {
        "createAndSendInboxEmail": {
            "emailSent": True,
            "errors": [],
            "inboxEmail": {"id": "e1"},
        }
    }

    async with webhook_session as session:
        result = await session.call_tool(
            "send_inbox_email",
            {
                "card_id": "card-1",
                "to": ["a@x.com"],
                "subject": "Hello",
                "body": "Hi there",
                "from_": "sender@pipefy.com",
            },
        )

    assert result.isError is False
    mock_webhook_client.send_inbox_email.assert_awaited_once_with(
        "card-1",
        ["a@x.com"],
        "Hello",
        "Hi there",
        from_="sender@pipefy.com",
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["result"]["createAndSendInboxEmail"]["emailSent"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_send_inbox_email_graphql_error(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.send_inbox_email.side_effect = TransportQueryError(
        "failed", errors=[{"message": "inbox not enabled"}]
    )

    async with webhook_session as session:
        result = await session.call_tool(
            "send_inbox_email",
            {
                "card_id": "card-1",
                "to": ["a@x.com"],
                "subject": "Hello",
                "body": "Hi",
                "from_": "sender@pipefy.com",
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "inbox not enabled" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_get_email_templates_success(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.get_email_templates.return_value = {
        "emailTemplates": {
            "edges": [
                {
                    "node": {
                        "id": "t1",
                        "name": "Follow-up",
                        "subject": "Hello {{card.title}}",
                    }
                }
            ]
        }
    }

    async with webhook_session as session:
        result = await session.call_tool(
            "get_email_templates",
            {"repo_id": "307061640"},
        )

    assert result.isError is False
    mock_webhook_client.get_email_templates.assert_awaited_once_with(
        "307061640",
        filter_by_name=None,
        first=50,
    )
    payload = extract_payload(result)
    assert payload["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_send_email_with_template_success(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.send_email_with_template.return_value = {
        "createAndSendInboxEmail": {
            "emailSent": True,
            "errors": [],
            "inboxEmail": {"id": "e1"},
        }
    }

    async with webhook_session as session:
        result = await session.call_tool(
            "send_email_with_template",
            {
                "card_id": "1320616225",
                "email_template_id": "42",
                "to": ["recipient@example.com"],
                "from_": "sender@pipefy.com",
            },
        )

    assert result.isError is False
    mock_webhook_client.send_email_with_template.assert_awaited_once_with(
        "1320616225",
        "42",
        to=["recipient@example.com"],
        from_="sender@pipefy.com",
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["result"]["createAndSendInboxEmail"]["emailSent"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_send_email_with_template_graphql_error(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.send_email_with_template.side_effect = TransportQueryError(
        "failed", errors=[{"message": "template not found"}]
    )

    async with webhook_session as session:
        result = await session.call_tool(
            "send_email_with_template",
            {
                "card_id": "1320616225",
                "email_template_id": "999",
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "template not found" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_send_email_with_template_rejects_non_numeric_card_id(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.send_email_with_template.side_effect = ValueError(
        "card_id must be a numeric card ID, got '550e8400-e29b-41d4-a716-446655440000'."
    )

    async with webhook_session as session:
        result = await session.call_tool(
            "send_email_with_template",
            {
                "card_id": "550e8400-e29b-41d4-a716-446655440000",
                "email_template_id": "42",
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "numeric card ID" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_create_webhook_rejects_http_url(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.create_webhook.side_effect = ValueError(
        "Invalid 'url': must be HTTPS. HTTP URLs are not allowed."
    )

    async with webhook_session as session:
        result = await session.call_tool(
            "create_webhook",
            {
                "pipe_id": "pipe-1",
                "url": "http://insecure.example.com/hook",
                "actions": ["card.create"],
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "HTTPS" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_get_card_inbox_emails_invalid_email_type(
    webhook_session, extract_payload
):
    async with webhook_session as session:
        result = await session.call_tool(
            "get_card_inbox_emails",
            {"card_id": "12345", "email_type": "draft"},
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "email_type" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_create_webhook_success(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.create_webhook.return_value = {
        "createWebhook": {
            "webhook": {
                "id": "w1",
                "url": "https://example.com/hook",
                "actions": ["card.create"],
            }
        }
    }

    async with webhook_session as session:
        result = await session.call_tool(
            "create_webhook",
            {
                "pipe_id": "pipe-1",
                "url": "https://example.com/hook",
                "actions": ["card.create"],
            },
        )

    assert result.isError is False
    mock_webhook_client.create_webhook.assert_awaited_once_with(
        "pipe-1", "https://example.com/hook", ["card.create"]
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["result"]["createWebhook"]["webhook"]["id"] == "w1"


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_create_webhook_graphql_error(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.create_webhook.side_effect = TransportQueryError(
        "failed", errors=[{"message": "invalid url"}]
    )

    async with webhook_session as session:
        result = await session.call_tool(
            "create_webhook",
            {
                "pipe_id": "pipe-1",
                "url": "https://example.com/hook",
                "actions": ["card.create"],
            },
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "invalid url" in payload["error"]


# ---------------------------------------------------------------------------
# get_webhooks / update_webhook
# ---------------------------------------------------------------------------


class TestGetWebhooks:
    @pytest.mark.anyio
    @pytest.mark.parametrize("webhook_session", [None], indirect=True)
    async def test_success(self, webhook_session, mock_webhook_client, extract_payload):
        mock_webhook_client.get_webhooks.return_value = {
            "pipe": {
                "webhooks": [
                    {
                        "id": "w1",
                        "name": "Hook A",
                        "url": "https://a.example/hook",
                        "actions": ["card.create"],
                        "headers": None,
                        "email": None,
                    }
                ]
            }
        }

        async with webhook_session as session:
            result = await session.call_tool(
                "get_webhooks",
                {"pipe_id": "601"},
            )

        assert result.isError is False
        mock_webhook_client.get_webhooks.assert_awaited_once_with("601")
        payload = extract_payload(result)
        assert payload["success"] is True
        assert len(payload["result"]["pipe"]["webhooks"]) == 1
        assert payload["result"]["pipe"]["webhooks"][0]["id"] == "w1"

    @pytest.mark.anyio
    @pytest.mark.parametrize("webhook_session", [None], indirect=True)
    async def test_empty(self, webhook_session, mock_webhook_client, extract_payload):
        mock_webhook_client.get_webhooks.return_value = {"pipe": {"webhooks": []}}

        async with webhook_session as session:
            result = await session.call_tool(
                "get_webhooks",
                {"pipe_id": "602"},
            )

        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["result"]["pipe"]["webhooks"] == []

    @pytest.mark.anyio
    @pytest.mark.parametrize("webhook_session", [None], indirect=True)
    async def test_graphql_error(
        self, webhook_session, mock_webhook_client, extract_payload
    ):
        mock_webhook_client.get_webhooks.side_effect = TransportQueryError(
            "failed", errors=[{"message": "pipe not found"}]
        )

        async with webhook_session as session:
            result = await session.call_tool(
                "get_webhooks",
                {"pipe_id": "999"},
            )

        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "pipe not found" in payload["error"]

    @pytest.mark.anyio
    @pytest.mark.parametrize("webhook_session", [None], indirect=True)
    async def test_has_read_only_hint(self, webhook_session):
        async with webhook_session as session:
            listed = await session.list_tools()
        tool = next(t for t in listed.tools if t.name == "get_webhooks")
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True


class TestUpdateWebhook:
    @pytest.mark.anyio
    @pytest.mark.parametrize("webhook_session", [None], indirect=True)
    async def test_success(self, webhook_session, mock_webhook_client, extract_payload):
        mock_webhook_client.update_webhook.return_value = {
            "updateWebhook": {
                "webhook": {
                    "id": "w1",
                    "name": "Renamed",
                    "url": "https://b.example/hook",
                    "actions": ["card.move"],
                    "headers": {},
                }
            }
        }

        async with webhook_session as session:
            result = await session.call_tool(
                "update_webhook",
                {
                    "webhook_id": "w1",
                    "name": "Renamed",
                    "url": "https://b.example/hook",
                    "actions": ["card.move"],
                    "headers": {},
                },
            )

        assert result.isError is False
        mock_webhook_client.update_webhook.assert_awaited_once_with(
            "w1",
            name="Renamed",
            url="https://b.example/hook",
            actions=["card.move"],
            headers={},
        )
        payload = extract_payload(result)
        assert payload["success"] is True
        assert payload["result"]["updateWebhook"]["webhook"]["id"] == "w1"

    @pytest.mark.anyio
    @pytest.mark.parametrize("webhook_session", [None], indirect=True)
    async def test_graphql_error(
        self, webhook_session, mock_webhook_client, extract_payload
    ):
        mock_webhook_client.update_webhook.side_effect = TransportQueryError(
            "failed", errors=[{"message": "webhook gone"}]
        )

        async with webhook_session as session:
            result = await session.call_tool(
                "update_webhook",
                {"webhook_id": "w1", "name": "X"},
            )

        assert result.isError is False
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "webhook gone" in payload["error"]

    @pytest.mark.anyio
    @pytest.mark.parametrize("webhook_session", [None], indirect=True)
    async def test_rejects_when_no_fields_to_update(
        self, webhook_session, mock_webhook_client, extract_payload
    ):
        async with webhook_session as session:
            result = await session.call_tool(
                "update_webhook",
                {"webhook_id": "w1"},
            )

        mock_webhook_client.update_webhook.assert_not_called()
        payload = extract_payload(result)
        assert payload["success"] is False
        assert "at least one" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_delete_webhook_preview_does_not_delete(
    webhook_session, mock_webhook_client, extract_payload
):
    async with webhook_session as session:
        result = await session.call_tool(
            "delete_webhook",
            {"webhook_id": "webhook-1"},
        )

    assert result.isError is False
    mock_webhook_client.delete_webhook.assert_not_called()
    payload = extract_payload(result)
    assert payload["success"] is False
    assert payload["requires_confirmation"] is True
    assert payload["resource"] == "webhook (ID: webhook-1)"
    assert "⚠️" in payload["message"]
    assert "confirm=True" in payload["message"]


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_delete_webhook_success(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.delete_webhook.return_value = {
        "deleteWebhook": {"success": True}
    }

    async with webhook_session as session:
        result = await session.call_tool(
            "delete_webhook",
            {"webhook_id": "webhook-1", "confirm": True},
        )

    assert result.isError is False
    mock_webhook_client.delete_webhook.assert_awaited_once_with("webhook-1")
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["result"]["deleteWebhook"]["success"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_delete_webhook_graphql_error(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.delete_webhook.side_effect = TransportQueryError(
        "failed", errors=[{"message": "webhook not found"}]
    )

    async with webhook_session as session:
        result = await session.call_tool(
            "delete_webhook",
            {"webhook_id": "w1", "confirm": True},
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "webhook not found" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_delete_webhook_has_destructive_hint(webhook_session):
    async with webhook_session as session:
        listed = await session.list_tools()
    delete_tool = next(t for t in listed.tools if t.name == "delete_webhook")
    assert delete_tool.annotations is not None
    assert delete_tool.annotations.destructiveHint is True
    assert delete_tool.annotations.readOnlyHint is False


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_get_card_inbox_emails_success(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.get_card_inbox_emails.return_value = {
        "card": {
            "id": "12345",
            "inbox_emails": [
                {
                    "id": "e1",
                    "type": "sent",
                    "subject": "Hello",
                    "from": "s@x.com",
                    "body": "Hi",
                },
                {
                    "id": "e2",
                    "type": "received",
                    "subject": "Re: Hello",
                    "from": "r@x.com",
                    "body": "Thanks",
                },
            ],
        }
    }

    async with webhook_session as session:
        result = await session.call_tool(
            "get_card_inbox_emails",
            {"card_id": "12345"},
        )

    assert result.isError is False
    mock_webhook_client.get_card_inbox_emails.assert_awaited_once_with(
        "12345", email_type=None
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert len(payload["result"]["card"]["inbox_emails"]) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_get_card_inbox_emails_with_type_filter(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.get_card_inbox_emails.return_value = {
        "card": {"id": "12345", "inbox_emails": [{"id": "e2", "type": "received"}]}
    }

    async with webhook_session as session:
        result = await session.call_tool(
            "get_card_inbox_emails",
            {"card_id": "12345", "email_type": "received"},
        )

    assert result.isError is False
    mock_webhook_client.get_card_inbox_emails.assert_awaited_once_with(
        "12345", email_type="received"
    )
    payload = extract_payload(result)
    assert payload["success"] is True
    assert payload["result"]["card"]["inbox_emails"][0]["type"] == "received"


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_get_card_inbox_emails_graphql_error(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.get_card_inbox_emails.side_effect = TransportQueryError(
        "failed", errors=[{"message": "card not found"}]
    )

    async with webhook_session as session:
        result = await session.call_tool(
            "get_card_inbox_emails",
            {"card_id": "99999"},
        )

    assert result.isError is False
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "card not found" in payload["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_get_card_inbox_emails_has_read_only_hint(webhook_session):
    async with webhook_session as session:
        listed = await session.list_tools()
    tool = next(t for t in listed.tools if t.name == "get_card_inbox_emails")
    assert tool.annotations is not None
    assert tool.annotations.readOnlyHint is True


## ---------------------------------------------------------------------------
## PipefyId coercion: int → str through MCP transport (mcporter mitigation)
## ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_get_email_templates_coerces_int_repo_id(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.get_email_templates.return_value = {
        "emailTemplates": {"edges": [], "pageInfo": {"hasNextPage": False}}
    }
    async with webhook_session as session:
        result = await session.call_tool("get_email_templates", {"repo_id": 301})
    assert result.isError is False
    mock_webhook_client.get_email_templates.assert_awaited_once_with(
        "301", filter_by_name=None, first=50
    )


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_get_card_inbox_emails_coerces_int_card_id(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.get_card_inbox_emails.return_value = {
        "card": {"inbox_emails": []}
    }
    async with webhook_session as session:
        result = await session.call_tool("get_card_inbox_emails", {"card_id": 555})
    assert result.isError is False
    mock_webhook_client.get_card_inbox_emails.assert_awaited_once_with(
        "555", email_type=None
    )


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_send_inbox_email_coerces_int_card_id(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.send_inbox_email.return_value = {
        "createAndSendInboxEmail": {
            "emailSent": True,
            "errors": [],
            "inboxEmail": {"id": "e1"},
        }
    }
    async with webhook_session as session:
        result = await session.call_tool(
            "send_inbox_email",
            {
                "card_id": 100,
                "to": ["a@x.com"],
                "subject": "Hi",
                "body": "Body",
                "from_": "s@x.com",
            },
        )
    assert result.isError is False
    mock_webhook_client.send_inbox_email.assert_awaited_once()
    call_args = mock_webhook_client.send_inbox_email.call_args
    assert call_args[0][0] == "100"


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_send_email_with_template_coerces_int_ids(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.send_email_with_template.return_value = {
        "createAndSendInboxEmail": {
            "emailSent": True,
            "errors": [],
            "inboxEmail": {"id": "e2"},
        }
    }
    async with webhook_session as session:
        result = await session.call_tool(
            "send_email_with_template",
            {"card_id": 200, "email_template_id": 55},
        )
    assert result.isError is False
    mock_webhook_client.send_email_with_template.assert_awaited_once()
    call_args = mock_webhook_client.send_email_with_template.call_args
    assert call_args[0][0] == "200"
    assert call_args[0][1] == "55"


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_create_webhook_coerces_int_pipe_id(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.create_webhook.return_value = {
        "createWebhook": {"webhook": {"id": "w1"}}
    }
    async with webhook_session as session:
        result = await session.call_tool(
            "create_webhook",
            {
                "pipe_id": 301,
                "url": "https://hooks.example.com/wh",
                "actions": ["card.create"],
            },
        )
    assert result.isError is False
    mock_webhook_client.create_webhook.assert_awaited_once()
    call_args = mock_webhook_client.create_webhook.call_args
    assert call_args[0][0] == "301"


# ---------------------------------------------------------------------------
# send_inbox_email — input validation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_send_inbox_email_rejects_empty_to_list(
    webhook_session, mock_webhook_client, extract_payload
):
    async with webhook_session as session:
        result = await session.call_tool(
            "send_inbox_email",
            {
                "card_id": "card-1",
                "to": [],
                "subject": "Hi",
                "body": "Body",
                "from_": "s@x.com",
            },
        )

    mock_webhook_client.send_inbox_email.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "'to'" in p["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_send_inbox_email_rejects_to_with_blank_items(
    webhook_session, mock_webhook_client, extract_payload
):
    async with webhook_session as session:
        result = await session.call_tool(
            "send_inbox_email",
            {
                "card_id": "card-1",
                "to": ["a@x.com", "   "],
                "subject": "Hi",
                "body": "Body",
                "from_": "s@x.com",
            },
        )

    mock_webhook_client.send_inbox_email.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "each recipient" in p["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_send_inbox_email_rejects_blank_subject(
    webhook_session, mock_webhook_client, extract_payload
):
    async with webhook_session as session:
        result = await session.call_tool(
            "send_inbox_email",
            {
                "card_id": "card-1",
                "to": ["a@x.com"],
                "subject": "   ",
                "body": "Body",
                "from_": "s@x.com",
            },
        )

    mock_webhook_client.send_inbox_email.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "'subject'" in p["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_send_inbox_email_rejects_blank_from(
    webhook_session, mock_webhook_client, extract_payload
):
    async with webhook_session as session:
        result = await session.call_tool(
            "send_inbox_email",
            {
                "card_id": "card-1",
                "to": ["a@x.com"],
                "subject": "Hi",
                "body": "Body",
                "from_": "   ",
            },
        )

    mock_webhook_client.send_inbox_email.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "'from_'" in p["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_send_inbox_email_rejects_invalid_card_id(
    webhook_session, mock_webhook_client, extract_payload
):
    async with webhook_session as session:
        result = await session.call_tool(
            "send_inbox_email",
            {
                "card_id": "",
                "to": ["a@x.com"],
                "subject": "Hi",
                "body": "Body",
                "from_": "s@x.com",
            },
        )

    mock_webhook_client.send_inbox_email.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "card_id" in p["error"]


# ---------------------------------------------------------------------------
# send_email_with_template — input validation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_send_email_with_template_rejects_blank_template_id(
    webhook_session, mock_webhook_client, extract_payload
):
    async with webhook_session as session:
        result = await session.call_tool(
            "send_email_with_template",
            {"card_id": "card-1", "email_template_id": "   "},
        )

    mock_webhook_client.send_email_with_template.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "email_template_id" in p["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_send_email_with_template_value_error_from_client(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.send_email_with_template.side_effect = ValueError(
        "Template has no subject or body."
    )

    async with webhook_session as session:
        result = await session.call_tool(
            "send_email_with_template",
            {"card_id": "card-1", "email_template_id": "42"},
        )

    p = extract_payload(result)
    assert p["success"] is False
    assert "Template has no subject or body" in p["error"]


# ---------------------------------------------------------------------------
# create_webhook — input validation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_create_webhook_rejects_blank_url(
    webhook_session, mock_webhook_client, extract_payload
):
    async with webhook_session as session:
        result = await session.call_tool(
            "create_webhook",
            {"pipe_id": "pipe-1", "url": "   ", "actions": ["card.create"]},
        )

    mock_webhook_client.create_webhook.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "'url'" in p["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_create_webhook_rejects_empty_actions_list(
    webhook_session, mock_webhook_client, extract_payload
):
    async with webhook_session as session:
        result = await session.call_tool(
            "create_webhook",
            {"pipe_id": "pipe-1", "url": "https://example.com/hook", "actions": []},
        )

    mock_webhook_client.create_webhook.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "'actions'" in p["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_create_webhook_rejects_invalid_pipe_id(
    webhook_session, mock_webhook_client, extract_payload
):
    async with webhook_session as session:
        result = await session.call_tool(
            "create_webhook",
            {
                "pipe_id": "",
                "url": "https://example.com/hook",
                "actions": ["card.create"],
            },
        )

    mock_webhook_client.create_webhook.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "pipe_id" in p["error"]


# ---------------------------------------------------------------------------
# get_email_templates — GraphQL error + input validation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_get_email_templates_graphql_error(
    webhook_session, mock_webhook_client, extract_payload
):
    mock_webhook_client.get_email_templates.side_effect = TransportQueryError(
        "failed", errors=[{"message": "pipe not found"}]
    )

    async with webhook_session as session:
        result = await session.call_tool(
            "get_email_templates",
            {"repo_id": "999"},
        )

    assert result.isError is False
    p = extract_payload(result)
    assert p["success"] is False
    assert "pipe not found" in p["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_get_email_templates_rejects_invalid_repo_id(
    webhook_session, mock_webhook_client, extract_payload
):
    async with webhook_session as session:
        result = await session.call_tool(
            "get_email_templates",
            {"repo_id": ""},
        )

    mock_webhook_client.get_email_templates.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "repo_id" in p["error"]


# ---------------------------------------------------------------------------
# get_card_inbox_emails — input validation (card_id)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_get_card_inbox_emails_rejects_invalid_card_id(
    webhook_session, mock_webhook_client, extract_payload
):
    async with webhook_session as session:
        result = await session.call_tool(
            "get_card_inbox_emails",
            {"card_id": ""},
        )

    mock_webhook_client.get_card_inbox_emails.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "card_id" in p["error"]


# ---------------------------------------------------------------------------
# send_email_with_template — invalid card_id
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_send_email_with_template_rejects_invalid_card_id(
    webhook_session, mock_webhook_client, extract_payload
):
    async with webhook_session as session:
        result = await session.call_tool(
            "send_email_with_template",
            {"card_id": "", "email_template_id": "42"},
        )

    mock_webhook_client.send_email_with_template.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "card_id" in p["error"]


# ---------------------------------------------------------------------------
# delete_webhook — GraphQL error with confirm=True (already covered above)
# and invalid webhook_id
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("webhook_session", [None], indirect=True)
async def test_delete_webhook_rejects_blank_webhook_id(
    webhook_session, mock_webhook_client, extract_payload
):
    async with webhook_session as session:
        result = await session.call_tool(
            "delete_webhook",
            {"webhook_id": "   "},
        )

    mock_webhook_client.delete_webhook.assert_not_called()
    p = extract_payload(result)
    assert p["success"] is False
    assert "webhook_id" in p["error"]
