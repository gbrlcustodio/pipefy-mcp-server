"""Tests for MCP client capability introspection helpers."""

from types import SimpleNamespace

from pipefy_mcp.tools.mcp_capabilities import supports_elicitation


def test_no_session_returns_false():
    ctx = SimpleNamespace()
    assert supports_elicitation(ctx) is False


def test_no_client_params_returns_false():
    ctx = SimpleNamespace(session=SimpleNamespace())
    assert supports_elicitation(ctx) is False


def test_no_capabilities_returns_false():
    session = SimpleNamespace(client_params=SimpleNamespace())
    ctx = SimpleNamespace(session=session)
    assert supports_elicitation(ctx) is False


def test_elicitation_false_returns_false():
    caps = SimpleNamespace(elicitation=False)
    session = SimpleNamespace(
        client_params=SimpleNamespace(capabilities=caps),
    )
    ctx = SimpleNamespace(session=session)
    assert supports_elicitation(ctx) is False


def test_elicitation_true_returns_true():
    caps = SimpleNamespace(elicitation=True)
    session = SimpleNamespace(
        client_params=SimpleNamespace(capabilities=caps),
    )
    ctx = SimpleNamespace(session=session)
    assert supports_elicitation(ctx) is True


def test_capabilities_without_elicitation_attr_returns_false():
    session = SimpleNamespace(
        client_params=SimpleNamespace(capabilities=SimpleNamespace()),
    )
    ctx = SimpleNamespace(session=session)
    assert supports_elicitation(ctx) is False
