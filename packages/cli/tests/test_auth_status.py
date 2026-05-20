"""Unit tests for `pipefy auth status`."""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipefy_cli.main import app
from pipefy_cli.oauth import RefreshError, StoredSession, storage

_ISSUER = "https://signin.example.com/realms/pipefy"
_CLIENT_ID = "pipefy-cli"
_ME = {"email": "user@pipefy.com", "name": "Pipefy User"}


def _seed_session(
    monkeypatch: pytest.MonkeyPatch,
    *,
    expires_in: int = 3600,
    refresh_expires_in: int = 2592000,
    obtained_at: int | None = None,
) -> None:
    """Plant a fresh stored session in the (faked) keyring."""
    if obtained_at is None:
        obtained_at = int(time.time())
    with monkeypatch.context() as mp:
        mp.setattr(time, "time", lambda: float(obtained_at))
        storage.store_session(
            issuer=_ISSUER,
            client_id=_CLIENT_ID,
            token_response={
                "access_token": "AT",
                "refresh_token": "RT",
                "token_type": "Bearer",
                "expires_in": expires_in,
                "refresh_expires_in": refresh_expires_in,
                "scope": "openid offline_access",
            },
        )


def _set_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPEFY_GRAPHQL_URL", "https://api.example.com/graphql")
    monkeypatch.setenv("PIPEFY_AUTH_URL", _ISSUER)
    monkeypatch.setenv("PIPEFY_AUTH_CLIENT_ID", _CLIENT_ID)


def _mock_client_with_me(me_payload: dict | None = _ME) -> MagicMock:
    client = MagicMock()
    client.get_me = AsyncMock(return_value=me_payload)
    return client


def _patch_command_client(client: MagicMock) -> Any:
    return patch(
        "pipefy_cli.commands.auth.get_authenticated_client", return_value=client
    )


@contextlib.contextmanager
def _patch_fresh_session(session: StoredSession | None) -> Iterator[None]:
    """Patch ``ensure_fresh_session`` at both call sites (command + ``get_authenticated_client``)."""
    with (
        patch("pipefy_cli.commands.auth.ensure_fresh_session", return_value=session),
        patch("pipefy_cli.auth.ensure_fresh_session", return_value=session),
    ):
        yield


def _invoke_status(runner: Any, args: list[str] | None = None) -> Any:
    return runner.invoke(app, ["auth", "status", *(args or [])])


# --------------------------------------------------------------------------- #
# Scenario 1: stored-session, fresh access token                              #
# --------------------------------------------------------------------------- #
def test_status_stored_session_active(
    clean_pipefy_env, saved_cwd, monkeypatch, runner, fake_keyring
):
    _set_auth_env(monkeypatch)
    _seed_session(monkeypatch)
    session = storage.load_session(issuer=_ISSUER, client_id=_CLIENT_ID)
    client = _mock_client_with_me()
    with _patch_fresh_session(session), _patch_command_client(client):
        result = _invoke_status(runner, ["--json"])

    assert result.exit_code == 0, (result.stdout or "") + (result.stderr or "")
    payload = json.loads(result.stdout)
    assert payload["signed_in"] is True
    assert payload["auth_source"] == "stored-session"
    assert payload["identity"] == _ME
    assert payload["state"] == "active"
    assert payload["issuer"] == _ISSUER
    assert payload["access_expires_at"] is not None
    assert payload["refresh_expires_at"] is not None
    assert payload["token_rejected"] is False
    assert payload["keychain_backend"]
    assert payload["masking_env_vars"] == []
    client.get_me.assert_awaited_once()


def test_status_stored_session_text_output(
    clean_pipefy_env, saved_cwd, monkeypatch, runner, fake_keyring
):
    _set_auth_env(monkeypatch)
    _seed_session(monkeypatch)
    session = storage.load_session(issuer=_ISSUER, client_id=_CLIENT_ID)
    client = _mock_client_with_me()
    with _patch_fresh_session(session), _patch_command_client(client):
        result = _invoke_status(runner)

    assert result.exit_code == 0
    assert "Signed in to Pipefy" in result.stdout
    assert _ME["email"] in result.stdout
    assert "stored session" in result.stdout
    assert "Expires:" in result.stdout


# --------------------------------------------------------------------------- #
# Scenario 2: stored-session, eager refresh runs (we mock the result as fresh) #
# --------------------------------------------------------------------------- #
def test_status_stored_session_rotates_via_refresh(
    clean_pipefy_env, saved_cwd, monkeypatch, runner, fake_keyring
):
    """If ensure_fresh_session returns a rotated session, status reports active."""
    _set_auth_env(monkeypatch)
    _seed_session(monkeypatch, expires_in=10)
    rotated = storage.StoredSession(
        issuer=_ISSUER,
        client_id=_CLIENT_ID,
        access_token="ROTATED",
        refresh_token="RT",
        token_type="Bearer",
        obtained_at=int(time.time()),
        expires_in=3600,
        refresh_expires_in=2592000,
        scope="openid offline_access",
        id_token=None,
    )
    client = _mock_client_with_me()
    with _patch_fresh_session(rotated), _patch_command_client(client):
        result = _invoke_status(runner, ["--json"])

    payload = json.loads(result.stdout)
    assert result.exit_code == 0
    assert payload["state"] == "active"
    assert payload["identity"] == _ME


# --------------------------------------------------------------------------- #
# Scenario 3: refresh-token grant rejects (invalid_grant)                     #
# --------------------------------------------------------------------------- #
def test_status_refresh_expired_exits_2(
    clean_pipefy_env, saved_cwd, monkeypatch, runner, fake_keyring
):
    _set_auth_env(monkeypatch)
    _seed_session(monkeypatch)
    with patch(
        "pipefy_cli.commands.auth.ensure_fresh_session",
        side_effect=RefreshError("Refresh failed (400): invalid_grant"),
    ):
        result = _invoke_status(runner, ["--json"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["auth_source"] == "stored-session"
    assert payload["state"] == "refresh-expired"
    # In --json mode the state field is the channel; no stderr commentary.
    assert (result.stderr or "") == ""


def test_status_refresh_expired_text_includes_relogin_hint(
    clean_pipefy_env, saved_cwd, monkeypatch, runner, fake_keyring
):
    _set_auth_env(monkeypatch)
    _seed_session(monkeypatch)
    with patch(
        "pipefy_cli.commands.auth.ensure_fresh_session",
        side_effect=RefreshError("Refresh failed (400): invalid_grant"),
    ):
        result = _invoke_status(runner)

    assert result.exit_code == 2
    assert "pipefy auth login" in (result.stderr or "")


# --------------------------------------------------------------------------- #
# Scenario 4: me returns 401 → token_rejected                                 #
# --------------------------------------------------------------------------- #
def test_status_me_401_marks_token_rejected(
    clean_pipefy_env, saved_cwd, monkeypatch, runner, fake_keyring
):
    from gql.transport.exceptions import TransportServerError

    _set_auth_env(monkeypatch)
    _seed_session(monkeypatch)
    session = storage.load_session(issuer=_ISSUER, client_id=_CLIENT_ID)
    client = MagicMock()
    client.get_me = AsyncMock(
        side_effect=TransportServerError("invalid_token", code=401)
    )
    with _patch_fresh_session(session), _patch_command_client(client):
        result = _invoke_status(runner, ["--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["signed_in"] is True
    assert payload["identity"] is None
    assert payload["token_rejected"] is True


def test_status_me_null_renders_identity_none(
    clean_pipefy_env, saved_cwd, monkeypatch, runner, fake_keyring
):
    """`me` is schema-nullable; when null, identity is reported as null at exit 0."""
    _set_auth_env(monkeypatch)
    _seed_session(monkeypatch)
    session = storage.load_session(issuer=_ISSUER, client_id=_CLIENT_ID)
    client = MagicMock()
    client.get_me = AsyncMock(return_value=None)
    with _patch_fresh_session(session), _patch_command_client(client):
        result = _invoke_status(runner, ["--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["signed_in"] is True
    assert payload["identity"] is None
    assert payload["token_rejected"] is False


def test_status_me_null_name_renders_email_only(
    clean_pipefy_env, saved_cwd, monkeypatch, runner, fake_keyring
):
    """`User.name` is nullable; text mode falls back to email-only."""
    _set_auth_env(monkeypatch)
    _seed_session(monkeypatch)
    session = storage.load_session(issuer=_ISSUER, client_id=_CLIENT_ID)
    client = MagicMock()
    client.get_me = AsyncMock(return_value={"email": "anon@pipefy.com", "name": None})
    with _patch_fresh_session(session), _patch_command_client(client):
        result = _invoke_status(runner)

    assert result.exit_code == 0
    assert "anon@pipefy.com" in result.stdout
    assert "(None)" not in result.stdout


def test_status_me_500_is_transport_error_not_token_rejected(
    clean_pipefy_env, saved_cwd, monkeypatch, runner, fake_keyring
):
    """A 5xx from upstream surfaces as transport error, NOT a credential rejection."""
    from gql.transport.exceptions import TransportServerError

    _set_auth_env(monkeypatch)
    _seed_session(monkeypatch)
    session = storage.load_session(issuer=_ISSUER, client_id=_CLIENT_ID)
    client = MagicMock()
    client.get_me = AsyncMock(
        side_effect=TransportServerError("upstream down", code=503)
    )
    with _patch_fresh_session(session), _patch_command_client(client):
        result = _invoke_status(runner, ["--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["token_rejected"] is False


# --------------------------------------------------------------------------- #
# Scenario 5: stored-session masked by PIPEFY_OAUTH_*                         #
# --------------------------------------------------------------------------- #
def test_status_service_account_wins_over_stored_session(
    clean_pipefy_env, saved_cwd, monkeypatch, runner, fake_keyring
):
    _set_auth_env(monkeypatch)
    _seed_session(monkeypatch)
    monkeypatch.setenv(
        "PIPEFY_INTERNAL_API_URL", "https://api.example.com/internal_api"
    )
    monkeypatch.setenv("PIPEFY_OAUTH_URL", "https://auth.example.com/oauth/token")
    monkeypatch.setenv("PIPEFY_OAUTH_CLIENT", "cid")
    monkeypatch.setenv("PIPEFY_OAUTH_SECRET", "csecret")
    client = _mock_client_with_me()
    with _patch_command_client(client):
        result = _invoke_status(runner, ["--json"])

    assert result.exit_code == 0, (result.stdout or "") + (result.stderr or "")
    payload = json.loads(result.stdout)
    assert payload["auth_source"] == "service-account"
    assert "service-account" in payload["detected_sources"]
    assert "stored-session" in payload["detected_sources"]
    assert payload["issuer"] is None
    assert payload["state"] == "n/a"


# --------------------------------------------------------------------------- #
# Scenario 6: stored-session masked by PIPEFY_TOKEN                           #
# --------------------------------------------------------------------------- #
def test_status_env_token_wins_over_stored_session(
    clean_pipefy_env, saved_cwd, monkeypatch, runner, fake_keyring
):
    _set_auth_env(monkeypatch)
    _seed_session(monkeypatch)
    monkeypatch.setenv("PIPEFY_TOKEN", "env-bearer")
    client = _mock_client_with_me()
    with _patch_command_client(client):
        result = _invoke_status(runner, ["--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["auth_source"] == "env-token"
    assert "env-token" in payload["detected_sources"]
    assert "stored-session" in payload["detected_sources"]


# --------------------------------------------------------------------------- #
# Scenario 7: --token flag                                                    #
# --------------------------------------------------------------------------- #
def test_status_flag_token(
    clean_pipefy_env, saved_cwd, monkeypatch, runner, fake_keyring
):
    monkeypatch.setenv("PIPEFY_GRAPHQL_URL", "https://api.example.com/graphql")
    client = _mock_client_with_me()
    with _patch_command_client(client):
        result = runner.invoke(
            app, ["--token", "flag-bearer", "auth", "status", "--json"]
        )

    assert result.exit_code == 0, (result.stdout or "") + (result.stderr or "")
    payload = json.loads(result.stdout)
    assert payload["auth_source"] == "flag-token"
    assert payload["identity"] == _ME
    assert payload["issuer"] is None
    assert payload["keychain_backend"] is None


# --------------------------------------------------------------------------- #
# Scenario 8: PIPEFY_TOKEN env var (no flag)                                  #
# --------------------------------------------------------------------------- #
def test_status_env_token_only(
    clean_pipefy_env, saved_cwd, monkeypatch, runner, fake_keyring
):
    monkeypatch.setenv("PIPEFY_GRAPHQL_URL", "https://api.example.com/graphql")
    monkeypatch.setenv("PIPEFY_TOKEN", "env-bearer")
    client = _mock_client_with_me()
    with _patch_command_client(client):
        result = _invoke_status(runner, ["--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["auth_source"] == "env-token"


# --------------------------------------------------------------------------- #
# Scenario 9: service-account only                                            #
# --------------------------------------------------------------------------- #
def test_status_service_account_only(
    clean_pipefy_env, saved_cwd, monkeypatch, runner, fake_keyring
):
    monkeypatch.setenv("PIPEFY_GRAPHQL_URL", "https://api.example.com/graphql")
    monkeypatch.setenv(
        "PIPEFY_INTERNAL_API_URL", "https://api.example.com/internal_api"
    )
    monkeypatch.setenv("PIPEFY_OAUTH_URL", "https://auth.example.com/oauth/token")
    monkeypatch.setenv("PIPEFY_OAUTH_CLIENT", "cid")
    monkeypatch.setenv("PIPEFY_OAUTH_SECRET", "csecret")
    client = _mock_client_with_me()
    with _patch_command_client(client):
        result = _invoke_status(runner, ["--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["auth_source"] == "service-account"
    assert payload["detected_sources"] == ["service-account"]


# --------------------------------------------------------------------------- #
# Scenario 10: no auth at all                                                 #
# --------------------------------------------------------------------------- #
def test_status_none_exits_2(
    clean_pipefy_env, saved_cwd, monkeypatch, runner, fake_keyring
):
    monkeypatch.setenv("PIPEFY_GRAPHQL_URL", "https://api.example.com/graphql")
    result = _invoke_status(runner, ["--json"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["signed_in"] is False
    assert payload["auth_source"] == "none"
    assert payload["detected_sources"] == []


def test_status_none_text_mentions_onboarding(
    clean_pipefy_env, saved_cwd, monkeypatch, runner, fake_keyring
):
    monkeypatch.setenv("PIPEFY_GRAPHQL_URL", "https://api.example.com/graphql")
    result = _invoke_status(runner)

    assert result.exit_code == 2
    assert "Not signed in" in result.stdout
    assert "pipefy auth login" in result.stdout
    assert "PIPEFY_TOKEN" in result.stdout
    assert "PIPEFY_OAUTH_*" in result.stdout
