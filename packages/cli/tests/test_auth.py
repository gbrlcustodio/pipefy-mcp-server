"""Tests for ``pipefy_cli.auth`` (OAuth / bearer factory and CLI exits)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer
from pipefy_sdk import PipefySettings

from pipefy_cli.auth import (
    AuthContext,
    BearerToken,
    OidcClient,
    get_authenticated_client,
)
from pipefy_cli.main import app
from pipefy_cli.oauth import StoredSession


def _minimal_oauth_settings() -> PipefySettings:
    return PipefySettings(
        graphql_url="https://unit.example.com/graphql",
        internal_api_url="https://unit.example.com/internal_api",
        oauth_url="https://unit.example.com/oauth/token",
        oauth_client="cid",
        oauth_secret="csecret",
    )


def _auth(
    *,
    bearer_token: str | None = None,
    bearer_source: str = "flag",
    issuer_url: str | None = None,
    client_id: str | None = None,
) -> AuthContext:
    """Build an :class:`AuthContext` for tests; constructs :class:`OidcClient` iff both halves are provided."""
    oidc_client = (
        OidcClient(issuer_url=issuer_url, client_id=client_id)
        if issuer_url and client_id
        else None
    )
    bearer = (
        BearerToken(value=bearer_token, source=bearer_source)  # type: ignore[arg-type]
        if bearer_token is not None
        else None
    )
    return AuthContext(bearer_token=bearer, oidc_client=oidc_client)


def test_get_authenticated_client_passes_bearer_to_pipefy_client(clean_pipefy_env):
    settings = _minimal_oauth_settings()
    with patch("pipefy_cli.auth.PipefyClient") as mock_pc:
        mock_pc.return_value = MagicMock()
        client = get_authenticated_client(settings, _auth(bearer_token="tok"))
        mock_pc.assert_called_once_with(settings, bearer_token="tok")
        assert client is mock_pc.return_value


def test_get_authenticated_client_oauth_mode_no_bearer(clean_pipefy_env):
    settings = _minimal_oauth_settings()
    with patch("pipefy_cli.auth.PipefyClient") as mock_pc:
        mock_pc.return_value = MagicMock()
        get_authenticated_client(settings, _auth())
        mock_pc.assert_called_once_with(settings)


def test_cache_returns_same_instance_for_identical_oauth_settings(clean_pipefy_env):
    settings = _minimal_oauth_settings()
    with patch("pipefy_cli.auth.PipefyClient") as mock_pc:
        mock_pc.return_value = MagicMock()
        first = get_authenticated_client(settings, _auth())
        second = get_authenticated_client(settings, _auth())
        assert first is second
        assert mock_pc.call_count == 1


def test_missing_graphql_exits_2_cli(clean_pipefy_env, saved_cwd, runner):
    result = runner.invoke(app, ["card", "get", "123"])
    assert result.exit_code == 2
    combined = (result.stderr or "") + (result.stdout or "")
    assert "docs/setup.md" in combined


def test_missing_oauth_exits_2_cli(clean_pipefy_env, saved_cwd, monkeypatch, runner):
    monkeypatch.setenv(
        "PIPEFY_GRAPHQL_URL",
        "https://oauth-missing.example.com/graphql",
    )
    result = runner.invoke(app, ["card", "get", "123"])
    assert result.exit_code == 2
    combined = (result.stderr or "") + (result.stdout or "")
    assert "docs/cli/auth.md" in combined


def test_cli_uses_pipefy_token_env_when_no_flag(
    clean_pipefy_env, saved_cwd, monkeypatch, runner
):
    monkeypatch.setenv(
        "PIPEFY_GRAPHQL_URL",
        "https://token-env.example.com/graphql",
    )
    monkeypatch.setenv("PIPEFY_TOKEN", "secret-from-env")
    mock_client = MagicMock()
    mock_client.get_card = AsyncMock(return_value={"id": "77"})
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ) as mock_gc:
        result = runner.invoke(app, ["card", "get", "77"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    mock_gc.assert_called_once()
    auth_arg = mock_gc.call_args.args[1]
    assert auth_arg.bearer_token == BearerToken(value="secret-from-env", source="env")


# --------------------------------------------------------------------------- #
# Priority 4: stored user session                                             #
# --------------------------------------------------------------------------- #


_FAR_FUTURE_EXPIRES_IN = 3600
_ISSUER = "https://signin.example.com/realms/pipefy"


def _fresh_stored_session(*, access_token: str = "SESSION_ACCESS") -> StoredSession:
    return StoredSession(
        issuer=_ISSUER,
        client_id="pipefy-cli",
        access_token=access_token,
        refresh_token="REFRESH",
        token_type="Bearer",
        obtained_at=int(time.time()),
        expires_in=_FAR_FUTURE_EXPIRES_IN,
        refresh_expires_in=None,
        scope="openid offline_access",
        id_token=None,
    )


def _public_only_settings() -> PipefySettings:
    """``PIPEFY_OAUTH_*`` triple absent → priority 3 unavailable, falls through to 4."""
    return PipefySettings(graphql_url="https://unit.example.com/graphql")


def test_bearer_token_wins_over_stored_session(clean_pipefy_env):
    """Priority 1/2 (bearer) MUST short-circuit before the keychain is even consulted."""
    settings = _minimal_oauth_settings()
    with (
        patch("pipefy_cli.auth.PipefyClient") as mock_pc,
        patch("pipefy_cli.auth.ensure_fresh_session") as mock_ensure,
    ):
        mock_pc.return_value = MagicMock()
        get_authenticated_client(
            settings,
            _auth(
                bearer_token="explicit-bearer",
                issuer_url=_ISSUER,
                client_id="pipefy-cli",
            ),
        )
        mock_pc.assert_called_once_with(settings, bearer_token="explicit-bearer")
        mock_ensure.assert_not_called()


def test_oauth_client_creds_wins_over_stored_session(clean_pipefy_env):
    """Priority 3 (full OAuth triple) MUST short-circuit before the keychain is consulted."""
    settings = _minimal_oauth_settings()
    with (
        patch("pipefy_cli.auth.PipefyClient") as mock_pc,
        patch("pipefy_cli.auth.InternalApiClient"),
        patch("pipefy_cli.auth.AiAutomationService"),
        patch("pipefy_cli.auth.ensure_fresh_session") as mock_ensure,
    ):
        mock_pc.return_value = MagicMock()
        get_authenticated_client(
            settings,
            _auth(issuer_url=_ISSUER, client_id="pipefy-cli"),
        )
        mock_pc.assert_called_once_with(settings)
        mock_ensure.assert_not_called()


def test_prefetched_session_skips_ensure_fresh_session(clean_pipefy_env):
    """``prefetched_session`` bypasses a second keychain read on the stored-session path."""
    settings = _public_only_settings()
    session = _fresh_stored_session()
    with (
        patch("pipefy_cli.auth.PipefyClient") as mock_pc,
        patch("pipefy_cli.auth.ensure_fresh_session") as mock_ensure,
    ):
        mock_pc.return_value = MagicMock()
        get_authenticated_client(
            settings,
            _auth(issuer_url=_ISSUER, client_id="pipefy-cli"),
            prefetched_session=session,
        )
        mock_ensure.assert_not_called()
        mock_pc.assert_called_once_with(settings, bearer_token=session.access_token)


def test_prefetched_session_does_not_override_bearer_precedence(clean_pipefy_env):
    """``prefetched_session`` must not bypass tiers 1/2 even when supplied."""
    settings = _public_only_settings()
    session = _fresh_stored_session()
    with (
        patch("pipefy_cli.auth.PipefyClient") as mock_pc,
        patch("pipefy_cli.auth.ensure_fresh_session") as mock_ensure,
    ):
        mock_pc.return_value = MagicMock()
        get_authenticated_client(
            settings,
            _auth(
                bearer_token="explicit-bearer",
                issuer_url=_ISSUER,
                client_id="pipefy-cli",
            ),
            prefetched_session=session,
        )
        mock_pc.assert_called_once_with(settings, bearer_token="explicit-bearer")
        mock_ensure.assert_not_called()


def test_stored_session_used_when_no_other_source(clean_pipefy_env):
    """Priority 4 activates when bearer absent AND OAuth triple incomplete."""
    settings = _public_only_settings()
    session = _fresh_stored_session()
    with (
        patch("pipefy_cli.auth.PipefyClient") as mock_pc,
        patch("pipefy_cli.auth.load_session", return_value=session),
        patch("pipefy_cli.auth.ensure_fresh_session", return_value=session),
    ):
        mock_pc.return_value = MagicMock()
        get_authenticated_client(
            settings, _auth(issuer_url=_ISSUER, client_id="pipefy-cli")
        )
        mock_pc.assert_called_once_with(settings, bearer_token=session.access_token)


def test_cache_invalidates_when_access_token_rotates(clean_pipefy_env):
    """Two calls with different rotated access tokens → two PipefyClient builds."""
    settings = _public_only_settings()
    stored = _fresh_stored_session()
    sessions = iter(
        [
            _fresh_stored_session(access_token="ROTATED_1"),
            _fresh_stored_session(access_token="ROTATED_2"),
        ]
    )
    with (
        patch("pipefy_cli.auth.PipefyClient") as mock_pc,
        patch("pipefy_cli.auth.load_session", return_value=stored),
        patch(
            "pipefy_cli.auth.ensure_fresh_session",
            side_effect=lambda **_: next(sessions),
        ),
    ):
        mock_pc.side_effect = [MagicMock(), MagicMock()]
        get_authenticated_client(
            settings, _auth(issuer_url=_ISSUER, client_id="pipefy-cli")
        )
        get_authenticated_client(
            settings, _auth(issuer_url=_ISSUER, client_id="pipefy-cli")
        )
        assert mock_pc.call_count == 2
        assert mock_pc.call_args_list[0].kwargs["bearer_token"] == "ROTATED_1"
        assert mock_pc.call_args_list[1].kwargs["bearer_token"] == "ROTATED_2"


def test_refresh_error_exits_2_with_relogin_hint(clean_pipefy_env, capsys):
    """RefreshError from ensure_fresh_session surfaces as exit(2) + relogin message."""
    from pipefy_cli.oauth import RefreshError

    settings = _public_only_settings()
    with (
        patch("pipefy_cli.auth.load_session", return_value=_fresh_stored_session()),
        patch(
            "pipefy_cli.auth.ensure_fresh_session",
            side_effect=RefreshError("invalid_grant"),
        ),
    ):
        with pytest.raises(typer.Exit) as excinfo:
            get_authenticated_client(
                settings, _auth(issuer_url=_ISSUER, client_id="pipefy-cli")
            )
        assert excinfo.value.exit_code == 2
    err = capsys.readouterr().err
    assert "Stored Pipefy session could not be refreshed" in err
    assert "pipefy auth login" in err
