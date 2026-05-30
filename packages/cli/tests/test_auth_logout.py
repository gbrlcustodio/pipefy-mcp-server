"""Unit tests for ``oauth/revoke.py`` and the ``pipefy auth logout`` command."""

from __future__ import annotations

import httpx
import pytest
from conftest import InMemoryKeyring
from pipefy_auth import revoke, storage
from pipefy_auth.responses import TokenResponse

from pipefy_cli.commands import auth as auth_module
from pipefy_cli.main import app as cli_app

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


# --------------------------------------------------------------------------- #
# Command — pipefy auth logout                                                #
# --------------------------------------------------------------------------- #


def _store_test_session(issuer: str = _ISSUER, client_id: str = "pipefy-cli") -> None:
    storage.store_session(
        issuer=issuer,
        client_id=client_id,
        token=TokenResponse(
            access_token="AAA",
            refresh_token="RRR",
            expires_in=300,
        ),
    )


class TestAuthLogoutCommand:
    def test_empty_auth_url_exits_2(
        self,
        runner,
        monkeypatch: pytest.MonkeyPatch,
        clean_pipefy_env,
        saved_cwd,
    ) -> None:
        """``PIPEFY_AUTH_URL=""`` is rejected at settings load and surfaces as exit 2."""
        monkeypatch.setenv("PIPEFY_AUTH_URL", "")
        result = runner.invoke(cli_app, ["auth", "logout"])
        assert result.exit_code == 2
        assert "auth_url" in result.stderr
        assert "should match pattern" in result.stderr

    def test_disable_stored_session_refuses_with_exit_2(
        self,
        runner,
        monkeypatch: pytest.MonkeyPatch,
        clean_pipefy_env,
        saved_cwd,
    ) -> None:
        """``PIPEFY_DISABLE_STORED_SESSION=1`` makes logout refuse before any keychain probe."""
        monkeypatch.setenv("PIPEFY_DISABLE_STORED_SESSION", "1")

        def _poison(**_kwargs: object):
            raise AssertionError(
                "revoke_session must not be called when sessions are disabled"
            )

        monkeypatch.setattr(auth_module, "revoke_session", _poison)

        result = runner.invoke(cli_app, ["auth", "logout"])
        assert result.exit_code == 2
        assert "Stored sessions are disabled" in result.stderr

    def test_no_session_is_idempotent(
        self,
        runner,
        monkeypatch: pytest.MonkeyPatch,
        fake_keyring: InMemoryKeyring,
        clean_pipefy_env,
        saved_cwd,
    ) -> None:
        monkeypatch.setenv("PIPEFY_AUTH_URL", _ISSUER)

        result = runner.invoke(cli_app, ["auth", "logout"])
        assert result.exit_code == 0, result.stderr
        assert "Not signed in. Nothing to do." in result.stdout
        assert result.stderr == ""

    def test_happy_path_revokes_and_deletes(
        self,
        runner,
        monkeypatch: pytest.MonkeyPatch,
        fake_keyring: InMemoryKeyring,
        clean_pipefy_env,
        saved_cwd,
    ) -> None:
        monkeypatch.setenv("PIPEFY_AUTH_URL", _ISSUER)
        _store_test_session()

        revoke_calls: list[tuple[str, str, str]] = []

        def _fake_revoke_session(
            *,
            issuer: str,
            client_id: str,
            refresh_token: str,
            policy=None,
            http_client=None,
        ) -> None:
            revoke_calls.append((issuer, client_id, refresh_token))

        monkeypatch.setattr(auth_module, "revoke_session", _fake_revoke_session)

        result = runner.invoke(cli_app, ["auth", "logout"])
        assert result.exit_code == 0, result.stderr
        assert revoke_calls == [(_ISSUER, "pipefy-cli", "RRR")]
        assert f"Signed out of Pipefy ({_ISSUER})." in result.stdout
        assert result.stderr == ""
        assert storage.load_session(issuer=_ISSUER, client_id="pipefy-cli") is None

    def test_revoke_network_failure_still_deletes_keychain(
        self,
        runner,
        monkeypatch: pytest.MonkeyPatch,
        fake_keyring: InMemoryKeyring,
        clean_pipefy_env,
        saved_cwd,
    ) -> None:
        monkeypatch.setenv("PIPEFY_AUTH_URL", _ISSUER)
        _store_test_session()

        def _boom(**_kwargs: object) -> None:
            raise revoke.RevocationError("Revocation request failed: ConnectError")

        monkeypatch.setattr(auth_module, "revoke_session", _boom)

        result = runner.invoke(cli_app, ["auth", "logout"])
        assert result.exit_code == 0, result.stderr
        assert f"Signed out of Pipefy ({_ISSUER})." in result.stdout
        assert "Could not revoke refresh token at the IdP" in result.stderr
        assert "may remain valid at the server" in result.stderr
        assert storage.load_session(issuer=_ISSUER, client_id="pipefy-cli") is None

    def test_keychain_delete_failure_after_revoke_exits_1(
        self,
        runner,
        monkeypatch: pytest.MonkeyPatch,
        fake_keyring: InMemoryKeyring,
        clean_pipefy_env,
        saved_cwd,
    ) -> None:
        """Revoke succeeds but keychain rejects delete: warn, don't claim sign-out, exit 1."""
        monkeypatch.setenv("PIPEFY_AUTH_URL", _ISSUER)
        _store_test_session()

        def _ok_revoke(**_kwargs: object) -> None:
            return None

        def _delete_boom(*, issuer: str, client_id: str) -> bool:
            raise storage.SessionDeleteError("Keychain is locked")

        monkeypatch.setattr(auth_module, "revoke_session", _ok_revoke)
        monkeypatch.setattr(auth_module, "delete_session", _delete_boom)

        result = runner.invoke(cli_app, ["auth", "logout"])
        assert result.exit_code == 1
        assert "Signed out of Pipefy" not in result.stdout
        assert "Could not delete local session from the keychain" in result.stderr
        assert "Keychain is locked" in result.stderr

    def test_end_session_unsupported_warns_and_deletes(
        self,
        runner,
        monkeypatch: pytest.MonkeyPatch,
        fake_keyring: InMemoryKeyring,
        clean_pipefy_env,
        saved_cwd,
    ) -> None:
        monkeypatch.setenv("PIPEFY_AUTH_URL", _ISSUER)
        _store_test_session()

        def _unsupported(**_kwargs: object) -> None:
            raise revoke.RevocationUnsupportedError(
                "OIDC provider does not advertise an end_session_endpoint."
            )

        monkeypatch.setattr(auth_module, "revoke_session", _unsupported)

        result = runner.invoke(cli_app, ["auth", "logout"])
        assert result.exit_code == 0, result.stderr
        assert f"Signed out of Pipefy ({_ISSUER})." in result.stdout
        assert "does not advertise a logout endpoint" in result.stderr
        assert storage.load_session(issuer=_ISSUER, client_id="pipefy-cli") is None
