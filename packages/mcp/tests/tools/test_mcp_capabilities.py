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


def test_advertised_elicitation_without_a_back_channel_returns_false():
    """Protocol revision 2026-07-28 advertises elicitation but cannot be called.

    A client on that revision still declares the ``elicitation`` capability in
    its request envelope, while ``can_send_request`` is ``False`` because the
    revision has no server-to-client channel. Gating on the capability alone
    lets ``ctx.elicit`` through, and it raises ``NoBackChannelError``.
    """
    caps = SimpleNamespace(elicitation=True)
    session = SimpleNamespace(
        client_params=SimpleNamespace(capabilities=caps),
        can_send_request=False,
    )
    ctx = SimpleNamespace(session=session)
    assert supports_elicitation(ctx) is False


def test_advertised_elicitation_with_a_back_channel_returns_true():
    caps = SimpleNamespace(elicitation=True)
    session = SimpleNamespace(
        client_params=SimpleNamespace(capabilities=caps),
        can_send_request=True,
    )
    ctx = SimpleNamespace(session=session)
    assert supports_elicitation(ctx) is True


def test_session_without_can_send_request_attr_is_treated_as_sendable():
    """An unmeasurable channel is attempted, not pre-emptively refused.

    Older SDKs and hand-built doubles expose no ``can_send_request``. Treating
    that as unsendable would silently disable elicitation everywhere it is
    absent; the ``NoBackChannelError`` handling at the elicitation call site is
    what covers the case where the channel really is missing.
    """
    caps = SimpleNamespace(elicitation=True)
    session = SimpleNamespace(client_params=SimpleNamespace(capabilities=caps))
    ctx = SimpleNamespace(session=session)
    assert supports_elicitation(ctx) is True
