"""Unit tests for ``pipefy_auth.discovery``: OIDC ``.well-known`` parsing."""

from __future__ import annotations

import httpx
import pytest

from pipefy_auth.discovery import DiscoveryPolicy, fetch_provider_metadata

_ISSUER = "https://signin.example.com/realms/pipefy"


def _discovery_payload(issuer: str = _ISSUER, **extra: str) -> dict[str, str]:
    payload = {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/protocol/openid-connect/auth",
        "token_endpoint": f"{issuer}/protocol/openid-connect/token",
    }
    payload.update(extra)
    return payload


def _client(payload: dict[str, str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/.well-known/openid-configuration")
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.unit
def test_jwks_uri_is_parsed_when_advertised() -> None:
    jwks = f"{_ISSUER}/protocol/openid-connect/certs"
    with _client(_discovery_payload(jwks_uri=jwks)) as client:
        metadata = fetch_provider_metadata(_ISSUER, client=client)
    assert metadata.jwks_uri == jwks


@pytest.mark.unit
def test_jwks_uri_is_none_when_absent() -> None:
    # The login flow does not read jwks_uri, so its absence must not break parsing.
    with _client(_discovery_payload()) as client:
        metadata = fetch_provider_metadata(_ISSUER, client=client)
    assert metadata.jwks_uri is None


@pytest.mark.unit
def test_insecure_jwks_uri_is_rejected() -> None:
    with _client(_discovery_payload(jwks_uri="http://internal/certs")) as client:
        with pytest.raises(ValueError, match="jwks_uri"):
            fetch_provider_metadata(_ISSUER, client=client)


@pytest.mark.unit
def test_insecure_jwks_uri_allowed_under_policy() -> None:
    jwks = "http://127.0.0.1:8080/certs"
    with _client(_discovery_payload(jwks_uri=jwks)) as client:
        metadata = fetch_provider_metadata(
            _ISSUER,
            policy=DiscoveryPolicy(allow_insecure_urls=True),
            client=client,
        )
    assert metadata.jwks_uri == jwks
