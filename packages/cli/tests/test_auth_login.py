"""Unit tests for the ``pipefy auth login`` command and its supporting OAuth pieces."""

from __future__ import annotations

import base64
import hashlib
import http.client
import threading
import time

import httpx
import keyring
import keyring.backend
import pytest

from pipefy_cli.main import app as cli_app
from pipefy_cli.oauth import discovery, flow, loopback, pkce, storage
from pipefy_cli.oauth.discovery import ProviderMetadata

# --------------------------------------------------------------------------- #
# PKCE                                                                        #
# --------------------------------------------------------------------------- #


class TestPkce:
    def test_verifier_within_rfc7636_bounds(self) -> None:
        for length in (43, 64, 128):
            v = pkce.generate_verifier(length)
            assert 43 <= len(v) <= 128
            assert all(ch.isalnum() or ch in "-._~" for ch in v)

    def test_verifier_rejects_out_of_range_length(self) -> None:
        with pytest.raises(ValueError):
            pkce.generate_verifier(42)
        with pytest.raises(ValueError):
            pkce.generate_verifier(129)

    def test_challenge_is_base64url_sha256_no_padding(self) -> None:
        verifier = "abc123" + "x" * 40  # 46 chars, within range
        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        assert pkce.challenge_from_verifier(verifier) == expected


# --------------------------------------------------------------------------- #
# Discovery                                                                   #
# --------------------------------------------------------------------------- #


def _discovery_payload(issuer: str = "https://example.test/realms/foo") -> dict:
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/protocol/openid-connect/auth",
        "token_endpoint": f"{issuer}/protocol/openid-connect/token",
    }


class _MockTransport(httpx.MockTransport):
    """httpx mock transport returning canned responses by URL."""


class TestDiscovery:
    def test_fetch_happy_path(self) -> None:
        payload = _discovery_payload()

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/.well-known/openid-configuration")
            return httpx.Response(200, json=payload)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        meta = discovery.fetch_provider_metadata(
            "https://example.test/realms/foo/", client=client
        )
        assert meta.issuer == payload["issuer"]
        assert meta.authorization_endpoint == payload["authorization_endpoint"]
        assert meta.token_endpoint == payload["token_endpoint"]

    def test_fetch_non_200_raises(self) -> None:
        client = httpx.Client(
            transport=httpx.MockTransport(lambda _r: httpx.Response(404, text="nope"))
        )
        with pytest.raises(ValueError, match="OIDC discovery failed"):
            discovery.fetch_provider_metadata("https://x.test/realms/y", client=client)

    def test_fetch_missing_field_raises(self) -> None:
        bad = {"issuer": "https://x.test", "token_endpoint": "https://x.test/t"}
        client = httpx.Client(
            transport=httpx.MockTransport(lambda _r: httpx.Response(200, json=bad))
        )
        with pytest.raises(ValueError, match="authorization_endpoint"):
            discovery.fetch_provider_metadata("https://x.test", client=client)


# --------------------------------------------------------------------------- #
# Loopback                                                                    #
# --------------------------------------------------------------------------- #


def _fire_callback(port: int, query: str) -> None:
    """Make a GET request to ``127.0.0.1:port/callback?<query>`` from a thread."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", f"/callback?{query}")
    conn.getresponse().read()
    conn.close()


class TestLoopback:
    def test_await_callback_returns_code_and_state(self) -> None:
        capture = loopback.LoopbackCapture()
        threading.Timer(
            0.1, _fire_callback, args=(capture.port, "code=abc&state=xyz")
        ).start()
        result = capture.await_callback(timeout=5.0)
        assert result.code == "abc"
        assert result.state == "xyz"
        assert result.error is None

    def test_await_callback_captures_error(self) -> None:
        capture = loopback.LoopbackCapture()
        threading.Timer(
            0.1,
            _fire_callback,
            args=(capture.port, "error=access_denied&error_description=user+aborted"),
        ).start()
        result = capture.await_callback(timeout=5.0)
        assert result.error == "access_denied"
        assert result.error_description == "user aborted"
        assert result.code is None

    def test_await_callback_times_out(self) -> None:
        capture = loopback.LoopbackCapture()
        with pytest.raises(TimeoutError):
            capture.await_callback(timeout=0.2)

    def test_redirect_uri_for_helper(self) -> None:
        assert loopback.redirect_uri_for(54321) == "http://127.0.0.1:54321/callback"

    def test_capture_redirect_uri_uses_bound_port(self) -> None:
        capture = loopback.LoopbackCapture()
        assert capture.redirect_uri == f"http://127.0.0.1:{capture.port}/callback"
        # Tear down the bound socket so we don't leak it between tests.
        capture._server.server_close()  # noqa: SLF001


# --------------------------------------------------------------------------- #
# Storage (keyring)                                                           #
# --------------------------------------------------------------------------- #


class _InMemoryKeyring(keyring.backend.KeyringBackend):
    """In-memory keyring backend that mirrors the real-world ``delete_password``
    contract (raises ``PasswordDeleteError`` when the entry is missing)."""

    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        from keyring.errors import PasswordDeleteError

        if (service, username) not in self._store:
            raise PasswordDeleteError(f"no entry for {service}/{username}")
        del self._store[(service, username)]


@pytest.fixture
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> _InMemoryKeyring:
    fake = _InMemoryKeyring()
    monkeypatch.setattr(keyring, "_keyring_backend", fake, raising=False)
    monkeypatch.setattr(keyring, "get_keyring", lambda: fake)
    monkeypatch.setattr(keyring, "set_password", fake.set_password)
    monkeypatch.setattr(keyring, "get_password", fake.get_password)
    monkeypatch.setattr(keyring, "delete_password", fake.delete_password)
    return fake


class TestStorage:
    def test_keychain_key_uses_host_and_client(self) -> None:
        key = storage.keychain_key(
            "https://Signin.Pipefy.com/realms/pipefy", "pipefy-cli"
        )
        assert key == "signin.pipefy.com|pipefy-cli"

    def test_store_then_load_roundtrip(self, fake_keyring: _InMemoryKeyring) -> None:
        token = {
            "access_token": "AAA",
            "refresh_token": "RRR",
            "token_type": "Bearer",
            "expires_in": 300,
            "refresh_expires_in": 3600,
            "scope": "openid email",
        }
        before = int(time.time())
        stored = storage.store_session(
            issuer="https://x.test/realms/foo",
            client_id="pipefy-cli",
            token_response=token,
        )
        assert stored.access_token == "AAA"
        assert stored.refresh_token == "RRR"
        assert stored.obtained_at >= before

        loaded = storage.load_session(
            issuer="https://x.test/realms/foo", client_id="pipefy-cli"
        )
        assert loaded is not None
        assert loaded.refresh_token == "RRR"
        assert loaded.scope == "openid email"

    def test_load_returns_none_when_absent(
        self, fake_keyring: _InMemoryKeyring
    ) -> None:
        assert (
            storage.load_session(issuer="https://x.test/realms/foo", client_id="cid")
            is None
        )

    def test_delete_reports_presence(self, fake_keyring: _InMemoryKeyring) -> None:
        storage.store_session(
            issuer="https://x.test/realms/foo",
            client_id="cid",
            token_response={"access_token": "a", "refresh_token": "r"},
        )
        assert storage.delete_session(
            issuer="https://x.test/realms/foo", client_id="cid"
        )
        assert not storage.delete_session(
            issuer="https://x.test/realms/foo", client_id="cid"
        )

    def test_store_rejects_missing_required_field(
        self, fake_keyring: _InMemoryKeyring
    ) -> None:
        with pytest.raises(ValueError, match="refresh_token"):
            storage.store_session(
                issuer="https://x.test/realms/foo",
                client_id="cid",
                token_response={"access_token": "a"},
            )


# --------------------------------------------------------------------------- #
# Flow                                                                        #
# --------------------------------------------------------------------------- #


class TestFlow:
    def test_build_authorization_url_has_all_required_params(self) -> None:
        meta = ProviderMetadata(
            issuer="https://x.test/realms/y",
            authorization_endpoint="https://x.test/realms/y/protocol/openid-connect/auth",
            token_endpoint="https://x.test/realms/y/protocol/openid-connect/token",
        )
        url = flow.build_authorization_url(
            metadata=meta,
            client_id="pipefy-cli",
            redirect_uri="http://127.0.0.1:5555/callback",
            code_challenge="ch4ll",
            state="st4t3",
        )
        for needle in (
            "client_id=pipefy-cli",
            "response_type=code",
            "redirect_uri=http%3A%2F%2F127.0.0.1%3A5555%2Fcallback",
            "code_challenge=ch4ll",
            "code_challenge_method=S256",
            "state=st4t3",
            "openid",
            "offline_access",
        ):
            assert needle in url

    def test_exchange_code_returns_token_dict(self) -> None:
        token_payload = {
            "access_token": "AAA",
            "refresh_token": "RRR",
            "token_type": "Bearer",
            "expires_in": 300,
        }

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert b"grant_type=authorization_code" in request.content
            assert b"code_verifier=ver1f1er" in request.content
            return httpx.Response(200, json=token_payload)

        meta = ProviderMetadata(
            issuer="i",
            authorization_endpoint="https://a/x",
            token_endpoint="https://t/x",
        )
        client = httpx.Client(transport=httpx.MockTransport(handler))
        result = flow.exchange_code(
            metadata=meta,
            client_id="pipefy-cli",
            code="thecode",
            redirect_uri="http://127.0.0.1:1/callback",
            code_verifier="ver1f1er",
            client=client,
        )
        assert result == token_payload

    def test_exchange_code_non_200_raises_login_error(self) -> None:
        meta = ProviderMetadata(
            issuer="i",
            authorization_endpoint="https://a/x",
            token_endpoint="https://t/x",
        )
        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda _r: httpx.Response(400, text='{"error":"invalid_grant"}')
            )
        )
        with pytest.raises(flow.LoginError, match="Token exchange failed"):
            flow.exchange_code(
                metadata=meta,
                client_id="cid",
                code="c",
                redirect_uri="r",
                code_verifier="v",
                client=client,
            )

    def test_run_login_state_mismatch_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Discovery returns canned metadata; loopback returns mismatched state.
        meta = ProviderMetadata(
            issuer="https://x.test/realms/y",
            authorization_endpoint="https://x.test/auth",
            token_endpoint="https://x.test/token",
        )
        monkeypatch.setattr(
            flow, "fetch_provider_metadata", lambda url, client=None: meta
        )

        class _FakeCapture:
            port = 12345
            redirect_uri = "http://127.0.0.1:12345/callback"

            def await_callback(self, *, timeout: float) -> loopback.CallbackResult:
                return loopback.CallbackResult(
                    code="abc", state="WRONG", error=None, error_description=None
                )

        monkeypatch.setattr(flow, "LoopbackCapture", _FakeCapture)
        with pytest.raises(flow.LoginError, match="State mismatch"):
            flow.run_login(
                issuer_url="https://x.test/realms/y",
                client_id="pipefy-cli",
                open_browser=lambda _u: True,
            )


# --------------------------------------------------------------------------- #
# Command                                                                     #
# --------------------------------------------------------------------------- #


@pytest.fixture
def cli_runner():
    from typer.testing import CliRunner

    return CliRunner(mix_stderr=False)


class TestAuthLoginCommand:
    def test_missing_auth_url_exits_2(
        self,
        cli_runner,
        monkeypatch: pytest.MonkeyPatch,
        clean_pipefy_env,
        saved_cwd,
    ) -> None:
        result = cli_runner.invoke(cli_app, ["auth", "login"])
        assert result.exit_code == 2
        assert "PIPEFY_AUTH_URL is required" in result.stderr

    def test_happy_path(
        self,
        cli_runner,
        monkeypatch: pytest.MonkeyPatch,
        fake_keyring: _InMemoryKeyring,
        clean_pipefy_env,
        saved_cwd,
    ) -> None:
        monkeypatch.setenv("PIPEFY_AUTH_URL", "https://x.test/realms/foo")
        monkeypatch.setenv("PIPEFY_AUTH_CLIENT_ID", "pipefy-cli")

        # Stub the entire OAuth flow at the run_login boundary so we don't need
        # a real browser or HTTP server in the test.
        def _fake_run_login(**_kwargs: object) -> flow.LoginResult:
            return flow.LoginResult(
                issuer="https://x.test/realms/foo",
                token_response={
                    "access_token": "AAA",
                    "refresh_token": "RRR",
                    "token_type": "Bearer",
                    "expires_in": 300,
                },
            )

        from pipefy_cli.commands import auth as auth_module

        monkeypatch.setattr(auth_module, "run_login", _fake_run_login)

        result = cli_runner.invoke(cli_app, ["auth", "login"])
        assert result.exit_code == 0, result.stderr
        assert "Signed in to Pipefy" in result.stdout

        loaded = storage.load_session(
            issuer="https://x.test/realms/foo", client_id="pipefy-cli"
        )
        assert loaded is not None
        assert loaded.refresh_token == "RRR"

    def test_masking_env_warning(
        self,
        cli_runner,
        monkeypatch: pytest.MonkeyPatch,
        fake_keyring: _InMemoryKeyring,
        clean_pipefy_env,
        saved_cwd,
    ) -> None:
        monkeypatch.setenv("PIPEFY_AUTH_URL", "https://x.test/realms/foo")
        monkeypatch.setenv("PIPEFY_TOKEN", "static-bearer-from-shell")

        from pipefy_cli.commands import auth as auth_module

        monkeypatch.setattr(
            auth_module,
            "run_login",
            lambda **_k: flow.LoginResult(
                issuer="https://x.test/realms/foo",
                token_response={"access_token": "A", "refresh_token": "R"},
            ),
        )

        result = cli_runner.invoke(cli_app, ["auth", "login"])
        assert result.exit_code == 0
        assert "PIPEFY_TOKEN" in result.stderr
        assert "other `pipefy` commands will continue to use it" in result.stderr

    def test_login_failure_exits_1(
        self,
        cli_runner,
        monkeypatch: pytest.MonkeyPatch,
        fake_keyring: _InMemoryKeyring,
        clean_pipefy_env,
        saved_cwd,
    ) -> None:
        monkeypatch.setenv("PIPEFY_AUTH_URL", "https://x.test/realms/foo")

        def _boom(**_kwargs: object) -> flow.LoginResult:
            raise flow.LoginError("Token exchange failed (400): invalid_grant")

        from pipefy_cli.commands import auth as auth_module

        monkeypatch.setattr(auth_module, "run_login", _boom)

        result = cli_runner.invoke(cli_app, ["auth", "login"])
        assert result.exit_code == 1
        assert "Login failed" in result.stderr
        assert "invalid_grant" in result.stderr
