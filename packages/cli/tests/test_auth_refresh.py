"""Unit tests for ``oauth/refresh.py`` — ``ensure_fresh_session`` + refresh grant."""

from __future__ import annotations

import time

import httpx
import pytest
from conftest import InMemoryKeyring

from pipefy_cli.oauth import refresh, storage

_ISSUER = "https://signin.example.com/realms/pipefy"
_CLIENT_ID = "pipefy-cli"


def _discovery_payload(issuer: str = _ISSUER) -> dict[str, str]:
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/protocol/openid-connect/auth",
        "token_endpoint": f"{issuer}/protocol/openid-connect/token",
    }


def _build_handler(
    *,
    discovery_status: int = 200,
    discovery_payload: dict | None = None,
    token_status: int = 200,
    token_payload: dict | None = None,
    raise_on_token: Exception | None = None,
):
    """Mock transport: returns canned responses for discovery + token endpoints."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                discovery_status, json=discovery_payload or _discovery_payload()
            )
        if request.url.path.endswith("/protocol/openid-connect/token"):
            if raise_on_token is not None:
                raise raise_on_token
            return httpx.Response(
                token_status,
                json=token_payload or {"access_token": "new", "refresh_token": "new_r"},
            )
        return httpx.Response(404)

    return handler


def _seed_session(
    monkeypatch: pytest.MonkeyPatch,
    *,
    obtained_at: int,
    expires_in: int = 300,
) -> None:
    """Persist a session whose ``obtained_at`` is pinned to ``obtained_at``.

    ``store_session`` stamps ``obtained_at`` via ``time.time()`` at write time, so
    we pin the clock for the single store call instead of writing-then-rewriting
    the keychain entry.
    """
    with monkeypatch.context() as mp:
        mp.setattr(time, "time", lambda: float(obtained_at))
        storage.store_session(
            issuer=_ISSUER,
            client_id=_CLIENT_ID,
            token_response={
                "access_token": "OLD",
                "refresh_token": "OLD_R",
                "token_type": "Bearer",
                "expires_in": expires_in,
                "scope": "openid offline_access",
            },
        )


# --------------------------------------------------------------------------- #
# ensure_fresh_session                                                        #
# --------------------------------------------------------------------------- #


class TestEnsureFreshSession:
    def test_returns_none_when_no_keychain_entry(
        self, fake_keyring: InMemoryKeyring
    ) -> None:
        assert (
            refresh.ensure_fresh_session(issuer=_ISSUER, client_id=_CLIENT_ID) is None
        )

    def test_returns_session_unchanged_when_fresh(
        self,
        fake_keyring: InMemoryKeyring,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _seed_session(monkeypatch, obtained_at=int(time.time()))  # full 300s ahead

        client = httpx.Client(transport=httpx.MockTransport(_build_handler()))
        result = refresh.ensure_fresh_session(
            issuer=_ISSUER,
            client_id=_CLIENT_ID,
            http_client=client,
        )
        assert result is not None
        assert result.access_token == "OLD"
        assert result.refresh_token == "OLD_R"

    def test_refreshes_when_within_leeway(
        self,
        fake_keyring: InMemoryKeyring,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # 30s lifetime + 60s leeway → must refresh.
        _seed_session(monkeypatch, obtained_at=int(time.time()) - 1, expires_in=30)

        client = httpx.Client(
            transport=httpx.MockTransport(
                _build_handler(
                    token_payload={
                        "access_token": "NEW_A",
                        "refresh_token": "NEW_R",
                        "token_type": "Bearer",
                        "expires_in": 300,
                    }
                )
            )
        )
        result = refresh.ensure_fresh_session(
            issuer=_ISSUER,
            client_id=_CLIENT_ID,
            http_client=client,
        )
        assert result is not None
        assert result.access_token == "NEW_A"
        assert result.refresh_token == "NEW_R"

    def test_persists_rotated_session(
        self,
        fake_keyring: InMemoryKeyring,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _seed_session(monkeypatch, obtained_at=int(time.time()) - 1, expires_in=30)
        client = httpx.Client(
            transport=httpx.MockTransport(
                _build_handler(
                    token_payload={
                        "access_token": "NEW_A",
                        "refresh_token": "NEW_R",
                    }
                )
            )
        )
        refresh.ensure_fresh_session(
            issuer=_ISSUER,
            client_id=_CLIENT_ID,
            http_client=client,
        )

        reloaded = storage.load_session(issuer=_ISSUER, client_id=_CLIENT_ID)
        assert reloaded is not None
        assert reloaded.access_token == "NEW_A"
        assert reloaded.refresh_token == "NEW_R"

    def test_carries_forward_omitted_lifetime_fields(
        self,
        fake_keyring: InMemoryKeyring,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When the IdP omits ``expires_in`` from the refresh response, the
        rotated session must inherit the previous value — otherwise the next
        freshness check would treat the token as already expired and force a
        refresh on the very next call."""
        _seed_session(monkeypatch, obtained_at=int(time.time()) - 1, expires_in=300)
        client = httpx.Client(
            transport=httpx.MockTransport(
                _build_handler(
                    token_payload={
                        "access_token": "NEW_A"
                    }  # no expires_in / scope / id_token
                )
            )
        )
        result = refresh.ensure_fresh_session(
            issuer=_ISSUER,
            client_id=_CLIENT_ID,
            http_client=client,
        )
        assert result is not None
        assert result.expires_in == 300  # carried forward
        assert result.scope == "openid offline_access"  # carried forward

    def test_falls_back_to_old_refresh_token_when_idp_does_not_rotate(
        self,
        fake_keyring: InMemoryKeyring,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _seed_session(monkeypatch, obtained_at=int(time.time()) - 1, expires_in=30)
        client = httpx.Client(
            transport=httpx.MockTransport(
                _build_handler(
                    # No refresh_token in response.
                    token_payload={"access_token": "NEW_A"}
                )
            )
        )
        result = refresh.ensure_fresh_session(
            issuer=_ISSUER,
            client_id=_CLIENT_ID,
            http_client=client,
        )
        assert result is not None
        assert result.refresh_token == "OLD_R"  # unchanged

    def test_obtained_at_updated_after_refresh(
        self,
        fake_keyring: InMemoryKeyring,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Seed an expired session relative to the pinned "now" so the freshness
        # check decides to refresh and store_session re-stamps obtained_at.
        _seed_session(monkeypatch, obtained_at=1_700_000_000 - 1, expires_in=30)
        client = httpx.Client(
            transport=httpx.MockTransport(
                _build_handler(
                    token_payload={
                        "access_token": "NEW_A",
                        "refresh_token": "NEW_R",
                    }
                )
            )
        )
        monkeypatch.setattr(time, "time", lambda: 1_700_000_000.0)
        result = refresh.ensure_fresh_session(
            issuer=_ISSUER,
            client_id=_CLIENT_ID,
            http_client=client,
        )
        assert result is not None
        assert result.obtained_at == 1_700_000_000

    def test_custom_leeway_forces_earlier_refresh(
        self,
        fake_keyring: InMemoryKeyring,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # 100s lifetime, with 90s leeway → must refresh because deadline = 10s ahead.
        _seed_session(monkeypatch, obtained_at=int(time.time()), expires_in=100)
        client = httpx.Client(
            transport=httpx.MockTransport(
                _build_handler(
                    token_payload={
                        "access_token": "REFRESHED_BECAUSE_LEEWAY",
                        "refresh_token": "NEW_R",
                    }
                )
            )
        )
        # leeway_s=200 forces the deadline into the past → refresh.
        result = refresh.ensure_fresh_session(
            issuer=_ISSUER,
            client_id=_CLIENT_ID,
            leeway_s=200,
            http_client=client,
        )
        assert result is not None
        assert result.access_token == "REFRESHED_BECAUSE_LEEWAY"

    def test_refresh_failure_does_not_delete_stored_session(
        self,
        fake_keyring: InMemoryKeyring,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _seed_session(monkeypatch, obtained_at=int(time.time()) - 1, expires_in=30)
        client = httpx.Client(
            transport=httpx.MockTransport(
                _build_handler(
                    token_status=400,
                    token_payload={"error": "invalid_grant"},
                )
            )
        )
        with pytest.raises(refresh.RefreshError):
            refresh.ensure_fresh_session(
                issuer=_ISSUER,
                client_id=_CLIENT_ID,
                http_client=client,
            )
        # Session is still present (user can retry / re-login).
        assert storage.load_session(issuer=_ISSUER, client_id=_CLIENT_ID) is not None


# --------------------------------------------------------------------------- #
# refresh_access_token (low-level)                                            #
# --------------------------------------------------------------------------- #


class TestRefreshAccessTokenErrors:
    def test_invalid_grant_carries_oauth_error_code(self) -> None:
        client = httpx.Client(
            transport=httpx.MockTransport(
                _build_handler(
                    token_status=400,
                    token_payload={"error": "invalid_grant"},
                )
            )
        )
        with pytest.raises(refresh.RefreshError) as exc_info:
            refresh.refresh_access_token(
                issuer=_ISSUER,
                client_id=_CLIENT_ID,
                refresh_token="x",
                http_client=client,
            )
        assert exc_info.value.error_code == "invalid_grant"
        assert "invalid_grant" in str(exc_info.value)

    def test_oauth_error_description_included_in_message(self) -> None:
        client = httpx.Client(
            transport=httpx.MockTransport(
                _build_handler(
                    token_status=400,
                    token_payload={
                        "error": "invalid_grant",
                        "error_description": "refresh token expired",
                    },
                )
            )
        )
        with pytest.raises(refresh.RefreshError) as exc_info:
            refresh.refresh_access_token(
                issuer=_ISSUER,
                client_id=_CLIENT_ID,
                refresh_token="x",
                http_client=client,
            )
        assert exc_info.value.error_code == "invalid_grant"
        assert "refresh token expired" in str(exc_info.value)

    def test_non_oauth_error_body_yields_generic_message_and_no_code(self) -> None:
        """Non-200 with non-JSON body must not echo the body and must not invent
        an ``error_code`` — callers branch on ``error_code``, not the message."""
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/.well-known/openid-configuration"):
                return httpx.Response(200, json=_discovery_payload())
            return httpx.Response(503, text="<html>upstream gateway timeout</html>")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with pytest.raises(refresh.RefreshError) as exc_info:
            refresh.refresh_access_token(
                issuer=_ISSUER,
                client_id=_CLIENT_ID,
                refresh_token="x",
                http_client=client,
            )
        assert exc_info.value.error_code is None
        assert "HTTP 503" in str(exc_info.value)
        assert "upstream gateway" not in str(exc_info.value)
        assert "<html>" not in str(exc_info.value)

    def test_error_response_does_not_echo_raw_body(self) -> None:
        """Regression guard for the same threat-model as ``flow._format_token_error``.

        A hostile or buggy IdP could include submitted params (e.g. the
        ``refresh_token`` itself) in its error response body. The structured
        scrub must never surface raw response text.
        """
        sentinel = "refresh_token=SENTINEL_REFRESH_LEAK"
        body = (
            '{"error":"invalid_grant","error_description":"bad refresh",'
            f'"echoed":"{sentinel}"}}'
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/.well-known/openid-configuration"):
                return httpx.Response(200, json=_discovery_payload())
            return httpx.Response(400, text=body)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with pytest.raises(refresh.RefreshError) as exc_info:
            refresh.refresh_access_token(
                issuer=_ISSUER,
                client_id=_CLIENT_ID,
                refresh_token="x",
                http_client=client,
            )
        message = str(exc_info.value)
        assert "invalid_grant" in message
        assert "bad refresh" in message
        assert sentinel not in message
        assert "SENTINEL_REFRESH_LEAK" not in message

    def test_network_error_raises_refresh_error(self) -> None:
        client = httpx.Client(
            transport=httpx.MockTransport(
                _build_handler(raise_on_token=httpx.ConnectError("boom"))
            )
        )
        with pytest.raises(refresh.RefreshError, match="Refresh request failed"):
            refresh.refresh_access_token(
                issuer=_ISSUER,
                client_id=_CLIENT_ID,
                refresh_token="x",
                http_client=client,
            )

    def test_discovery_failure_raises_refresh_error(self) -> None:
        client = httpx.Client(
            transport=httpx.MockTransport(_build_handler(discovery_status=404))
        )
        with pytest.raises(refresh.RefreshError, match="OIDC discovery failed"):
            refresh.refresh_access_token(
                issuer=_ISSUER,
                client_id=_CLIENT_ID,
                refresh_token="x",
                http_client=client,
            )

    def test_non_object_json_raises_refresh_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/.well-known/openid-configuration"):
                return httpx.Response(200, json=_discovery_payload())
            return httpx.Response(200, json=["not", "an", "object"])

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with pytest.raises(refresh.RefreshError, match="non-object"):
            refresh.refresh_access_token(
                issuer=_ISSUER,
                client_id=_CLIENT_ID,
                refresh_token="x",
                http_client=client,
            )
