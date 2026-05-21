"""Unit tests for ``oauth/revoke.py`` (the ``pipefy auth logout`` command lands next)."""

from __future__ import annotations

import httpx
import pytest

from pipefy_cli.oauth import revoke

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

_ISSUER = "https://example.test/realms/foo"
_LOGOUT_URL = f"{_ISSUER}/protocol/openid-connect/logout"


def _discovery_payload(*, include_end_session: bool = True) -> dict:
    payload: dict = {
        "issuer": _ISSUER,
        "authorization_endpoint": f"{_ISSUER}/protocol/openid-connect/auth",
        "token_endpoint": f"{_ISSUER}/protocol/openid-connect/token",
    }
    if include_end_session:
        payload["end_session_endpoint"] = _LOGOUT_URL
    return payload


def _make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# --------------------------------------------------------------------------- #
# revoke_session                                                              #
# --------------------------------------------------------------------------- #


class TestRevokeSession:
    def test_happy_path_204(self) -> None:
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/.well-known/openid-configuration"):
                return httpx.Response(200, json=_discovery_payload())
            assert request.method == "POST"
            assert str(request.url) == _LOGOUT_URL
            seen["body"] = request.content
            return httpx.Response(204)

        revoke.revoke_session(
            issuer=_ISSUER,
            client_id="pipefy-cli",
            refresh_token="rt_value",
            http_client=_make_client(handler),
        )
        body = seen["body"]
        assert isinstance(body, (bytes, bytearray))
        assert b"client_id=pipefy-cli" in body
        assert b"refresh_token=rt_value" in body

    def test_end_session_endpoint_absent_raises_unsupported(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json=_discovery_payload(include_end_session=False)
            )

        with pytest.raises(revoke.RevocationUnsupportedError):
            revoke.revoke_session(
                issuer=_ISSUER,
                client_id="pipefy-cli",
                refresh_token="rt",
                http_client=_make_client(handler),
            )

    def test_network_error_raises_revocation_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/.well-known/openid-configuration"):
                return httpx.Response(200, json=_discovery_payload())
            raise httpx.ConnectError("connection refused")

        with pytest.raises(revoke.RevocationError, match="Revocation request failed"):
            revoke.revoke_session(
                issuer=_ISSUER,
                client_id="pipefy-cli",
                refresh_token="rt",
                http_client=_make_client(handler),
            )

    def test_non_2xx_raises_with_status_only(self) -> None:
        # Regression sentinel: body must not leak into the error message.
        sentinel = "SENTINEL_REVOKE_LEAK"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/.well-known/openid-configuration"):
                return httpx.Response(200, json=_discovery_payload())
            return httpx.Response(
                400, text=f'{{"error":"invalid_token","echo":"{sentinel}"}}'
            )

        with pytest.raises(revoke.RevocationError) as exc_info:
            revoke.revoke_session(
                issuer=_ISSUER,
                client_id="pipefy-cli",
                refresh_token="rt",
                http_client=_make_client(handler),
            )
        message = str(exc_info.value)
        assert "400" in message
        assert sentinel not in message
        assert "invalid_token" not in message

    def test_discovery_failure_raises_revocation_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="nope")

        with pytest.raises(revoke.RevocationError, match="OIDC discovery failed"):
            revoke.revoke_session(
                issuer=_ISSUER,
                client_id="pipefy-cli",
                refresh_token="rt",
                http_client=_make_client(handler),
            )
