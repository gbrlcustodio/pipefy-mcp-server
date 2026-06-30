"""Tests for ``pipefy_cli.auth`` (resolver wiring, eager warmup, CLI exits)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer
from pipefy_auth import (
    OidcClient,
    RefreshableBearerAuth,
    ServiceAccount,
    StaticBearerAuth,
    StaticTokenAuth,
    StoredSession,
    StoredSessionAuth,
    TokenResponse,
)
from pipefy_sdk import PipefySettings

from pipefy_cli.auth import (
    AuthContext,
    BearerToken,
    get_authenticated_client,
    to_display_source,
)
from pipefy_cli.main import app


def _minimal_settings() -> PipefySettings:
    return PipefySettings(base_url="https://unit.example.com")


def _service_account() -> ServiceAccount:
    return ServiceAccount(
        token_url="https://unit.example.com/oauth/token",
        client_id="cid",
        client_secret="csecret",
    )


def _auth(
    *,
    bearer_token: str | None = None,
    bearer_source: str = "flag",
    issuer_url: str | None = None,
    client_id: str | None = None,
    service_account: ServiceAccount | None = None,
    include_service_account: bool = True,
) -> AuthContext:
    """Build an :class:`AuthContext` for tests."""
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
    sa = (
        service_account
        if service_account is not None
        else (_service_account() if include_service_account else None)
    )
    return AuthContext(bearer_token=bearer, service_account=sa, oidc_client=oidc_client)


def test_get_authenticated_client_passes_auth_to_pipefy_client(clean_pipefy_env):
    settings = _minimal_settings()
    with patch("pipefy_cli.auth.PipefyClient") as mock_pc:
        mock_pc.return_value = MagicMock()
        client = get_authenticated_client(settings, _auth(bearer_token="tok"))
        kwargs = mock_pc.call_args.kwargs
        assert mock_pc.call_args.args == (settings,)
        assert isinstance(kwargs["auth"], StaticBearerAuth)
        assert kwargs["surface"] == "cli"
        assert client is mock_pc.return_value


def test_cache_returns_same_instance_for_identical_service_account_settings(
    clean_pipefy_env,
):
    settings = _minimal_settings()
    with patch("pipefy_cli.auth.PipefyClient") as mock_pc:
        mock_pc.return_value = MagicMock()
        first = get_authenticated_client(settings, _auth())
        second = get_authenticated_client(settings, _auth())
        assert first is second
        assert mock_pc.call_count == 1


def test_empty_base_url_exits_2_cli(clean_pipefy_env, saved_cwd, monkeypatch, runner):
    """``PIPEFY_BASE_URL=""`` is rejected at settings load and surfaces as exit 2."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "")
    result = runner.invoke(app, ["card", "get", "123"])
    assert result.exit_code == 2
    combined = (result.stderr or "") + (result.stdout or "")
    # Pydantic error references the field name ``base_url`` (mapped from
    # ``PIPEFY_BASE_URL`` via ``env_prefix``).
    assert "base_url" in combined
    assert "should match pattern" in combined


def test_missing_oauth_exits_2_cli(
    clean_pipefy_env, saved_cwd, monkeypatch, runner, fake_keyring
):
    # ``fake_keyring`` isolates the stored-session tier from the host's real
    # OS keychain. Without it, the prod-default ``auth_url`` would let a
    # developer's actual stored session bypass the missing-oauth exit and
    # fail this test with a stale-refresh error.
    monkeypatch.setenv(
        "PIPEFY_BASE_URL",
        "https://oauth-missing.example.com",
    )
    result = runner.invoke(app, ["card", "get", "123"])
    assert result.exit_code == 2
    combined = (result.stderr or "") + (result.stdout or "")
    assert "docs/cli/auth.md" in combined


def test_cli_uses_pipefy_token_env_when_no_flag(
    clean_pipefy_env, saved_cwd, monkeypatch, runner
):
    monkeypatch.setenv(
        "PIPEFY_BASE_URL",
        "https://token-env.example.com",
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
# Display source mapping                                                      #
# --------------------------------------------------------------------------- #


def test_to_display_source_maps_flag_token_to_flag_label():
    """``--token`` source surfaces as the locked ``flag-token`` wire value."""
    source = to_display_source(
        StaticTokenAuth("t"), BearerToken(value="t", source="flag")
    )
    assert source == "flag-token"


def test_to_display_source_maps_env_token_to_env_label():
    """``PIPEFY_TOKEN`` source surfaces as the locked ``env-token`` wire value."""
    source = to_display_source(
        StaticTokenAuth("t"), BearerToken(value="t", source="env")
    )
    assert source == "env-token"


# --------------------------------------------------------------------------- #
# Stored user session                                                         #
# --------------------------------------------------------------------------- #


_FAR_FUTURE_EXPIRES_IN = 3600
_ISSUER = "https://signin.example.com/realms/pipefy"


def _fresh_stored_session(*, access_token: str = "SESSION_ACCESS") -> StoredSession:
    return StoredSession(
        issuer=_ISSUER,
        client_id="pipefy-cli",
        obtained_at=int(time.time()),
        token=TokenResponse(
            access_token=access_token,
            refresh_token="REFRESH",
            expires_in=_FAR_FUTURE_EXPIRES_IN,
            scope="openid offline_access",
        ),
    )


def _public_only_settings() -> PipefySettings:
    """``PIPEFY_SERVICE_ACCOUNT_*`` triple absent → service-account tier unavailable, stored session wins."""
    return PipefySettings(base_url="https://unit.example.com")


def _public_only_auth(
    *,
    bearer_token: str | None = None,
    bearer_source: str = "flag",
    issuer_url: str | None = None,
    client_id: str | None = None,
) -> AuthContext:
    """``AuthContext`` without a service-account tier (stored-session scenario)."""
    return _auth(
        bearer_token=bearer_token,
        bearer_source=bearer_source,
        issuer_url=issuer_url,
        client_id=client_id,
        include_service_account=False,
    )


def test_bearer_token_wins_over_stored_session(clean_pipefy_env):
    """The static-token tier MUST short-circuit before the keychain is even consulted."""
    settings = _minimal_settings()
    with (
        patch("pipefy_cli.auth.PipefyClient") as mock_pc,
        patch("pipefy_auth.resolver.load_session") as mock_load,
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
        assert isinstance(mock_pc.call_args.kwargs["auth"], StaticBearerAuth)
        mock_ensure.assert_not_called()
        mock_load.assert_not_called()


def test_service_account_creds_win_over_stored_session(clean_pipefy_env):
    """The service-account tier MUST short-circuit before the keychain is consulted."""
    settings = _minimal_settings()
    with (
        patch("pipefy_cli.auth.PipefyClient") as mock_pc,
        patch("pipefy_auth.resolver.load_session") as mock_load,
        patch("pipefy_cli.auth.ensure_fresh_session") as mock_ensure,
    ):
        mock_pc.return_value = MagicMock()
        get_authenticated_client(
            settings,
            _auth(issuer_url=_ISSUER, client_id="pipefy-cli"),
        )
        mock_pc.assert_called_once()
        mock_ensure.assert_not_called()
        mock_load.assert_not_called()


def test_stored_session_used_when_no_other_source(clean_pipefy_env):
    """Stored-session tier activates when bearer absent and service-account triple incomplete."""
    settings = _public_only_settings()
    session = _fresh_stored_session()
    with (
        patch("pipefy_cli.auth.PipefyClient") as mock_pc,
        patch("pipefy_auth.resolver.load_session", return_value=session),
        patch("pipefy_cli.auth.ensure_fresh_session", return_value=session),
    ):
        mock_pc.return_value = MagicMock()
        get_authenticated_client(
            settings,
            _public_only_auth(issuer_url=_ISSUER, client_id="pipefy-cli"),
        )
        mock_pc.assert_called_once()
        assert isinstance(mock_pc.call_args.kwargs["auth"], RefreshableBearerAuth)


def test_cache_reuses_resolved_auth_for_stored_session(clean_pipefy_env):
    """Two stored-session calls with identical OIDC inputs reuse the cached client."""
    settings = _public_only_settings()
    stored = _fresh_stored_session()
    with (
        patch("pipefy_cli.auth.PipefyClient") as mock_pc,
        patch("pipefy_auth.resolver.load_session", return_value=stored),
        patch("pipefy_cli.auth.ensure_fresh_session", return_value=stored),
    ):
        mock_pc.return_value = MagicMock()
        first = get_authenticated_client(
            settings,
            _public_only_auth(issuer_url=_ISSUER, client_id="pipefy-cli"),
        )
        second = get_authenticated_client(
            settings,
            _public_only_auth(issuer_url=_ISSUER, client_id="pipefy-cli"),
        )
        assert first is second
        assert mock_pc.call_count == 1


def test_refresh_error_exits_2_with_relogin_hint(clean_pipefy_env, capsys):
    """RefreshError from the eager warmup surfaces as exit(2) + relogin message."""
    from pipefy_auth import RefreshError

    settings = _public_only_settings()
    with (
        patch(
            "pipefy_auth.resolver.load_session", return_value=_fresh_stored_session()
        ),
        patch("pipefy_cli.auth.resolve_pipefy_auth") as mock_resolve,
        patch(
            "pipefy_cli.auth.ensure_fresh_session",
            side_effect=RefreshError("invalid_grant"),
        ),
    ):
        # Return the stored-session variant so the eager warmup path runs.
        mock_resolve.return_value = StoredSessionAuth(
            OidcClient(issuer_url=_ISSUER, client_id="pipefy-cli")
        )
        with pytest.raises(typer.Exit) as excinfo:
            get_authenticated_client(
                settings,
                _public_only_auth(issuer_url=_ISSUER, client_id="pipefy-cli"),
            )
        assert excinfo.value.exit_code == 2
    err = capsys.readouterr().err
    assert "Stored Pipefy session could not be refreshed" in err
    assert "pipefy auth login" in err
