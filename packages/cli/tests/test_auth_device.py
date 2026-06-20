"""Unit tests for OAuth device authorization grant (``pipefy auth login --device``)."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from conftest import InMemoryKeyring
from pipefy_auth import device, discovery, storage
from pipefy_auth.flow import LoginError, LoginResult
from pipefy_auth.responses import TokenResponse
from typer.testing import CliRunner

from pipefy_cli.main import app as cli_app

# Rich/Typer renders option names like ``--no-browser`` in bold by default,
# splitting the dashes with ``\x1b[1m`` ANSI codes on Linux CI runners under
# ``FORCE_COLOR=1``. Strip them before the substring assert so the test passes
# on both macOS and Linux without depending on env vars.
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner(mix_stderr=False)


_ISSUER = "https://x.test/realms/foo"
_DEVICE_PATH = "/protocol/openid-connect/auth/device"
_TOKEN_PATH = "/protocol/openid-connect/token"


def _discovery_json(*, include_device: bool = True) -> dict[str, Any]:
    body: dict[str, Any] = {
        "issuer": _ISSUER,
        "authorization_endpoint": f"{_ISSUER}/protocol/openid-connect/auth",
        "token_endpoint": f"{_ISSUER}{_TOKEN_PATH}",
    }
    if include_device:
        body["device_authorization_endpoint"] = f"{_ISSUER}{_DEVICE_PATH}"
    return body


def _token_success() -> dict[str, Any]:
    return {
        "access_token": "AAA",
        "refresh_token": "RRR",
        "token_type": "Bearer",
        "expires_in": 300,
    }


def _clock_sleep_pair() -> tuple[
    list[float], Callable[[float], None], Callable[[], float]
]:
    clock: list[float] = [0.0]

    def monotonic() -> float:
        return clock[0]

    def sleep(dt: float) -> None:
        clock[0] += dt

    return clock, sleep, monotonic


def _device_meta() -> discovery.ProviderMetadata:
    return discovery.ProviderMetadata(
        issuer=_ISSUER,
        authorization_endpoint=f"{_ISSUER}/auth",
        token_endpoint=f"{_ISSUER}{_TOKEN_PATH}",
        device_authorization_endpoint=f"{_ISSUER}{_DEVICE_PATH}",
    )


def _device_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "device_code": "dc",
        "user_code": "ABCD",
        "verification_uri": "https://x.test/verify",
        "expires_in": 60,
    }
    payload.update(overrides)
    return payload


class TestDeviceAuthorizationFromPayload:
    def test_minimal_payload_parses(self) -> None:
        dev = device.DeviceAuthorization.from_payload(_device_payload())
        assert dev.device_code == "dc"
        assert dev.user_code == "ABCD"
        assert dev.expires_in == 60
        assert dev.interval == 5  # default when absent
        assert dev.verification_uri_complete is None

    @pytest.mark.parametrize(
        "missing_field",
        ("device_code", "user_code", "verification_uri", "expires_in"),
    )
    def test_missing_required_field_raises_value_error(
        self, missing_field: str
    ) -> None:
        payload = _device_payload()
        del payload[missing_field]
        with pytest.raises(ValueError, match=missing_field):
            device.DeviceAuthorization.from_payload(payload)

    def test_invalid_expires_in_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="expires_in"):
            device.DeviceAuthorization.from_payload(
                _device_payload(expires_in="not-a-number")
            )

    def test_invalid_interval_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="interval"):
            device.DeviceAuthorization.from_payload(
                _device_payload(interval="not-a-number")
            )

    def test_zero_interval_defaults_to_five(self) -> None:
        dev = device.DeviceAuthorization.from_payload(_device_payload(interval=0))
        assert dev.interval == 5

    def test_empty_verification_uri_complete_becomes_none(self) -> None:
        dev = device.DeviceAuthorization.from_payload(
            _device_payload(verification_uri_complete="")
        )
        assert dev.verification_uri_complete is None


class TestRequestDeviceAuthorization:
    def test_missing_endpoint_raises_login_error(self) -> None:
        meta = discovery.ProviderMetadata(
            issuer=_ISSUER,
            authorization_endpoint=f"{_ISSUER}/auth",
            token_endpoint=f"{_ISSUER}{_TOKEN_PATH}",
            device_authorization_endpoint=None,
        )
        client = httpx.Client(
            transport=httpx.MockTransport(lambda _r: httpx.Response(404))
        )
        with pytest.raises(LoginError, match="device_authorization_endpoint"):
            device.request_device_authorization(
                metadata=meta,
                client_id="pipefy-cli",
                code_challenge="test-challenge",
                client=client,
            )

    def test_non_200_renders_oauth_error(self) -> None:
        def handler(_r: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={"error": "invalid_client", "error_description": "bad client"},
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with pytest.raises(LoginError, match="invalid_client.*bad client"):
            device.request_device_authorization(
                metadata=_device_meta(),
                client_id="pipefy-cli",
                code_challenge="test-challenge",
                client=client,
            )

    def test_non_json_body_raises_login_error(self) -> None:
        def handler(_r: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>oops</html>")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with pytest.raises(LoginError, match="non-JSON"):
            device.request_device_authorization(
                metadata=_device_meta(),
                client_id="pipefy-cli",
                code_challenge="test-challenge",
                client=client,
            )

    def test_parse_failure_wraps_value_error_as_login_error(self) -> None:
        def handler(_r: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_device_payload(expires_in="abc"))

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with pytest.raises(LoginError, match="expires_in"):
            device.request_device_authorization(
                metadata=_device_meta(),
                client_id="pipefy-cli",
                code_challenge="test-challenge",
                client=client,
            )


class TestDiscoveryDeviceEndpoint:
    def test_parses_and_validates_device_endpoint(self) -> None:
        payload = _discovery_json()

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/openid-configuration")
            return httpx.Response(200, json=payload)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        meta = discovery.fetch_provider_metadata(_ISSUER, client=client)
        assert (
            meta.device_authorization_endpoint
            == payload["device_authorization_endpoint"]
        )

    def test_missing_device_endpoint_is_none(self) -> None:
        payload = _discovery_json(include_device=False)
        client = httpx.Client(
            transport=httpx.MockTransport(lambda _r: httpx.Response(200, json=payload))
        )
        meta = discovery.fetch_provider_metadata(_ISSUER, client=client)
        assert meta.device_authorization_endpoint is None

    def test_invalid_device_endpoint_ssrf(self) -> None:
        payload = _discovery_json()
        payload["device_authorization_endpoint"] = "https://127.0.0.1/device"
        client = httpx.Client(
            transport=httpx.MockTransport(lambda _r: httpx.Response(200, json=payload))
        )
        with pytest.raises(ValueError, match="device_authorization_endpoint"):
            discovery.fetch_provider_metadata(_ISSUER, client=client)


class TestRunDeviceLogin:
    def _client_for(
        self, handler: Callable[[httpx.Request], httpx.Response]
    ) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_sends_pkce_on_device_auth_and_token_poll(self) -> None:
        from urllib.parse import parse_qs

        from pipefy_auth.pkce import challenge_from_verifier

        captured: dict[str, dict[str, list[str]]] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if request.method == "GET" and path.endswith("/openid-configuration"):
                return httpx.Response(200, json=_discovery_json())
            if request.method == "POST" and path.endswith(_DEVICE_PATH):
                captured["device"] = parse_qs(request.content.decode("utf-8"))
                return httpx.Response(200, json=_device_payload(interval=0))
            if request.method == "POST" and path.endswith(_TOKEN_PATH):
                captured["token"] = parse_qs(request.content.decode("utf-8"))
                return httpx.Response(200, json=_token_success())
            return httpx.Response(404)

        _, sleep, monotonic = _clock_sleep_pair()
        device.run_device_login(
            issuer_url=_ISSUER,
            client_id="pipefy-cli",
            http_client=self._client_for(handler),
            sleep=sleep,
            monotonic=monotonic,
        )

        device_form = captured["device"]
        assert device_form["code_challenge_method"] == ["S256"]
        challenge = device_form["code_challenge"][0]
        verifier = captured["token"]["code_verifier"][0]
        # Challenge must derive from the verifier sent on the poll — without
        # this binding a PKCE-enforcing IdP rejects the token exchange even if
        # the device-auth call accepted the params.
        assert challenge_from_verifier(verifier) == challenge

    def test_happy_path(self) -> None:
        polls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if request.method == "GET" and path.endswith("/openid-configuration"):
                return httpx.Response(200, json=_discovery_json())
            if request.method == "POST" and path.endswith(_DEVICE_PATH):
                return httpx.Response(
                    200,
                    json={
                        "device_code": "devc",
                        "user_code": "ABCD-EFGH",
                        "verification_uri": "https://x.test/verify",
                        "expires_in": 120,
                        "interval": 0,
                    },
                )
            if request.method == "POST" and path.endswith(_TOKEN_PATH):
                polls["n"] += 1
                return httpx.Response(200, json=_token_success())
            return httpx.Response(404)

        clock, sleep, monotonic = _clock_sleep_pair()
        infos: list[device.DeviceAuthorization] = []

        result = device.run_device_login(
            issuer_url=_ISSUER,
            client_id="pipefy-cli",
            http_client=self._client_for(handler),
            sleep=sleep,
            monotonic=monotonic,
            on_device_info=infos.append,
        )
        assert isinstance(result, LoginResult)
        assert result.issuer == _ISSUER
        assert result.token.access_token == "AAA"
        assert polls["n"] == 1
        # First poll fires immediately (RFC 8628 §3.5: the wait applies
        # *between* requests after authorization_pending, not before the first).
        assert clock[0] == 0.0
        assert len(infos) == 1
        assert infos[0].user_code == "ABCD-EFGH"

    def test_authorization_pending_then_success(self) -> None:
        polls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if request.method == "GET" and path.endswith("/openid-configuration"):
                return httpx.Response(200, json=_discovery_json())
            if request.method == "POST" and path.endswith(_DEVICE_PATH):
                return httpx.Response(
                    200,
                    json={
                        "device_code": "devc",
                        "user_code": "ZZZZ-ZZZZ",
                        "verification_uri": "https://x.test/verify",
                        "expires_in": 120,
                        "interval": 0,
                    },
                )
            if request.method == "POST" and path.endswith(_TOKEN_PATH):
                n = polls["n"]
                polls["n"] += 1
                if n == 0:
                    return httpx.Response(400, json={"error": "authorization_pending"})
                return httpx.Response(200, json=_token_success())
            return httpx.Response(404)

        _, sleep, monotonic = _clock_sleep_pair()
        result = device.run_device_login(
            issuer_url=_ISSUER,
            client_id="pipefy-cli",
            http_client=self._client_for(handler),
            sleep=sleep,
            monotonic=monotonic,
        )
        assert result.token.refresh_token == "RRR"
        assert polls["n"] == 2

    def test_slow_down_then_success(self) -> None:
        polls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if request.method == "GET" and path.endswith("/openid-configuration"):
                return httpx.Response(200, json=_discovery_json())
            if request.method == "POST" and path.endswith(_DEVICE_PATH):
                return httpx.Response(
                    200,
                    json={
                        "device_code": "devc",
                        "user_code": "AAAA-BBBB",
                        "verification_uri": "https://x.test/verify",
                        "expires_in": 120,
                        "interval": 0,
                    },
                )
            if request.method == "POST" and path.endswith(_TOKEN_PATH):
                n = polls["n"]
                polls["n"] += 1
                if n == 0:
                    return httpx.Response(400, json={"error": "slow_down"})
                return httpx.Response(200, json=_token_success())
            return httpx.Response(404)

        _, sleep, monotonic = _clock_sleep_pair()
        result = device.run_device_login(
            issuer_url=_ISSUER,
            client_id="pipefy-cli",
            http_client=self._client_for(handler),
            sleep=sleep,
            monotonic=monotonic,
        )
        assert result.token.access_token == "AAA"
        assert polls["n"] == 2

    def test_expired_token_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if request.method == "GET" and path.endswith("/openid-configuration"):
                return httpx.Response(200, json=_discovery_json())
            if request.method == "POST" and path.endswith(_DEVICE_PATH):
                return httpx.Response(
                    200,
                    json={
                        "device_code": "devc",
                        "user_code": "XXXX-YYYY",
                        "verification_uri": "https://x.test/verify",
                        "expires_in": 120,
                        "interval": 0,
                    },
                )
            if request.method == "POST" and path.endswith(_TOKEN_PATH):
                return httpx.Response(400, json={"error": "expired_token"})
            return httpx.Response(404)

        _, sleep, monotonic = _clock_sleep_pair()
        with pytest.raises(LoginError, match="didn't complete in time"):
            device.run_device_login(
                issuer_url=_ISSUER,
                client_id="pipefy-cli",
                http_client=self._client_for(handler),
                sleep=sleep,
                monotonic=monotonic,
            )

    def test_client_deadline_expires_without_server_expired_token(self) -> None:
        polls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if request.method == "GET" and path.endswith("/openid-configuration"):
                return httpx.Response(200, json=_discovery_json())
            if request.method == "POST" and path.endswith(_DEVICE_PATH):
                return httpx.Response(
                    200,
                    json={
                        "device_code": "devc",
                        "user_code": "TIME-OUT",
                        "verification_uri": "https://x.test/verify",
                        "expires_in": 10,
                        "interval": 5,
                    },
                )
            if request.method == "POST" and path.endswith(_TOKEN_PATH):
                polls["n"] += 1
                return httpx.Response(400, json={"error": "authorization_pending"})
            return httpx.Response(404)

        _, sleep, monotonic = _clock_sleep_pair()
        with pytest.raises(LoginError, match="didn't complete in time"):
            device.run_device_login(
                issuer_url=_ISSUER,
                client_id="pipefy-cli",
                http_client=self._client_for(handler),
                sleep=sleep,
                monotonic=monotonic,
            )
        assert polls["n"] == 2

    def test_access_denied_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if request.method == "GET" and path.endswith("/openid-configuration"):
                return httpx.Response(200, json=_discovery_json())
            if request.method == "POST" and path.endswith(_DEVICE_PATH):
                return httpx.Response(
                    200,
                    json={
                        "device_code": "devc",
                        "user_code": "QQQQ-WWWW",
                        "verification_uri": "https://x.test/verify",
                        "expires_in": 120,
                        "interval": 0,
                    },
                )
            if request.method == "POST" and path.endswith(_TOKEN_PATH):
                return httpx.Response(400, json={"error": "access_denied"})
            return httpx.Response(404)

        _, sleep, monotonic = _clock_sleep_pair()
        with pytest.raises(LoginError, match="cancelled"):
            device.run_device_login(
                issuer_url=_ISSUER,
                client_id="pipefy-cli",
                http_client=self._client_for(handler),
                sleep=sleep,
                monotonic=monotonic,
            )


class TestAuthLoginDeviceCommand:
    def test_device_login_happy_path(
        self,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
        fake_keyring: InMemoryKeyring,
        clean_pipefy_env: None,
        saved_cwd: object,
    ) -> None:
        monkeypatch.setenv("PIPEFY_AUTH_URL", _ISSUER)
        monkeypatch.setenv("PIPEFY_AUTH_CLIENT_ID", "pipefy-cli")

        from pipefy_auth.device import DeviceAuthorization

        from pipefy_cli.commands import auth as auth_module

        def _fake_run_device_login(**kwargs: object) -> LoginResult:
            cb = kwargs.get("on_device_info")
            if cb is not None:
                cb(
                    DeviceAuthorization(
                        device_code="dc",
                        user_code="USER-CODE",
                        verification_uri="https://x.test/v",
                        verification_uri_complete="https://x.test/vc",
                        expires_in=60,
                        interval=1,
                    )
                )
            return LoginResult(
                issuer=_ISSUER,
                token=TokenResponse(
                    access_token="AAA",
                    refresh_token="RRR",
                    expires_in=300,
                ),
            )

        monkeypatch.setattr(auth_module, "run_device_login", _fake_run_device_login)

        result = cli_runner.invoke(cli_app, ["auth", "login", "--device"])
        assert result.exit_code == 0, result.stderr
        assert "USER-CODE" in result.stdout
        assert "https://x.test/vc" in result.stdout
        assert "Signed in to Pipefy" in result.stdout

        loaded = storage.load_session(issuer=_ISSUER, client_id="pipefy-cli")
        assert loaded is not None
        assert loaded.token.refresh_token == "RRR"

    def test_device_with_no_browser_errors(
        self,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
        fake_keyring: InMemoryKeyring,
        clean_pipefy_env: None,
        saved_cwd: object,
    ) -> None:
        monkeypatch.setenv("PIPEFY_AUTH_URL", _ISSUER)
        result = cli_runner.invoke(
            cli_app, ["auth", "login", "--device", "--no-browser"]
        )
        assert result.exit_code != 0
        assert "--no-browser is incompatible" in _ANSI_ESCAPE_RE.sub("", result.stderr)

    def test_device_with_explicit_callback_timeout_errors(
        self,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
        fake_keyring: InMemoryKeyring,
        clean_pipefy_env: None,
        saved_cwd: object,
    ) -> None:
        monkeypatch.setenv("PIPEFY_AUTH_URL", _ISSUER)
        result = cli_runner.invoke(
            cli_app, ["auth", "login", "--device", "--callback-timeout", "60"]
        )
        assert result.exit_code != 0
        assert "--callback-timeout is incompatible" in _ANSI_ESCAPE_RE.sub(
            "", result.stderr
        )

    def test_device_with_default_callback_timeout_ok(
        self,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
        fake_keyring: InMemoryKeyring,
        clean_pipefy_env: None,
        saved_cwd: object,
    ) -> None:
        # Guard against false positives in the parameter-source check: invoking
        # --device WITHOUT --callback-timeout must not error out on the conflict
        # detector.
        monkeypatch.setenv("PIPEFY_AUTH_URL", _ISSUER)
        monkeypatch.setenv("PIPEFY_AUTH_CLIENT_ID", "pipefy-cli")

        from pipefy_cli.commands import auth as auth_module

        def _fake_run_device_login(**_kwargs: object) -> LoginResult:
            return LoginResult(
                issuer=_ISSUER,
                token=TokenResponse(access_token="A", refresh_token="R"),
            )

        monkeypatch.setattr(auth_module, "run_device_login", _fake_run_device_login)

        result = cli_runner.invoke(cli_app, ["auth", "login", "--device"])
        assert result.exit_code == 0, result.stderr
