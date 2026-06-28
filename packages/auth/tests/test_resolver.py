"""Unit tests for ``pipefy_auth.resolver`` (fixed three-tier precedence chain)."""

from __future__ import annotations

import time

import pytest
from httpx_auth import OAuth2ClientCredentials

from pipefy_auth.bearer import (
    CallableBearerAuth,
    RefreshableBearerAuth,
    StaticBearerAuth,
)
from pipefy_auth.identity import OidcClient
from pipefy_auth.refresh import RefreshError
from pipefy_auth.resolver import (
    SERVICE_ACCOUNT_TIER,
    STATIC_TOKEN_TIER,
    STORED_SESSION_TIER,
    ServiceAccount,
    detect_pipefy_tiers,
    missing_auth_message,
    resolve_pipefy_auth,
    tier_for,
)
from pipefy_auth.responses import TokenResponse
from pipefy_auth.storage import StoredSession


def _stored_session() -> StoredSession:
    return StoredSession(
        issuer="https://issuer.test/realms/pipefy",
        client_id="pipefy-cli",
        obtained_at=int(time.time()),
        token=TokenResponse(
            access_token="ACCESS",
            refresh_token="REFRESH",
            token_type="Bearer",
            expires_in=3600,
            refresh_expires_in=None,
            scope=None,
            id_token=None,
        ),
    )


def _service_account() -> ServiceAccount:
    return ServiceAccount(token_url="https://t/", client_id="c", client_secret="s")


def _oidc() -> OidcClient:
    return OidcClient(issuer_url="https://issuer.test/", client_id="pipefy-cli")


@pytest.mark.unit
def test_resolve_with_no_inputs_returns_none():
    assert resolve_pipefy_auth() is None


@pytest.mark.unit
def test_static_token_wins_and_short_circuits_lower_tiers(monkeypatch):
    """Once the static-token tier resolves, lower tiers' inputs are never inspected."""
    mock_load = MockCounter()
    monkeypatch.setattr("pipefy_auth.resolver.load_session", mock_load)
    resolved = resolve_pipefy_auth(
        static_token="TOKEN",
        service_account=_service_account(),
        oidc_client=_oidc(),
    )
    assert isinstance(resolved, StaticBearerAuth)
    assert tier_for(resolved) == STATIC_TOKEN_TIER
    assert mock_load.calls == 0


@pytest.mark.unit
def test_static_token_trimmed_and_blank_treated_as_absent():
    assert resolve_pipefy_auth(static_token="   ") is None
    resolved = resolve_pipefy_auth(static_token="  ABC  ")
    assert isinstance(resolved, StaticBearerAuth)


@pytest.mark.unit
def test_service_account_wins_when_no_static_token_and_short_circuits_stored(
    monkeypatch,
):
    mock_load = MockCounter()
    monkeypatch.setattr("pipefy_auth.resolver.load_session", mock_load)
    resolved = resolve_pipefy_auth(
        service_account=_service_account(), oidc_client=_oidc()
    )
    assert isinstance(resolved, OAuth2ClientCredentials)
    assert tier_for(resolved) == SERVICE_ACCOUNT_TIER
    assert mock_load.calls == 0


@pytest.mark.unit
def test_stored_session_wins_when_nothing_else_configured(monkeypatch):
    monkeypatch.setattr(
        "pipefy_auth.resolver.load_session", lambda **_: _stored_session()
    )
    resolved = resolve_pipefy_auth(oidc_client=_oidc())
    assert isinstance(resolved, RefreshableBearerAuth)
    assert tier_for(resolved) == STORED_SESSION_TIER


@pytest.mark.unit
def test_stored_session_tier_requires_keychain_entry(monkeypatch):
    monkeypatch.setattr("pipefy_auth.resolver.load_session", lambda **_: None)
    assert resolve_pipefy_auth(oidc_client=_oidc()) is None


@pytest.mark.unit
def test_resolver_skips_stored_session_when_oidc_client_is_none(monkeypatch):
    """``oidc_client=None`` (kill-switch path) skips the keychain entirely."""

    def _poison(**_kwargs):
        raise AssertionError("load_session must not be called when oidc_client is None")

    monkeypatch.setattr("pipefy_auth.resolver.load_session", _poison)
    assert resolve_pipefy_auth(oidc_client=None) is None


@pytest.mark.unit
def test_detect_omits_stored_session_when_oidc_client_is_none(monkeypatch):
    """``detect_pipefy_tiers`` skips the stored-session probe with no client."""

    def _poison(**_kwargs):
        raise AssertionError("load_session must not be called when oidc_client is None")

    monkeypatch.setattr("pipefy_auth.resolver.load_session", _poison)
    tiers = detect_pipefy_tiers(
        static_token="T",
        service_account=_service_account(),
        oidc_client=None,
    )
    assert tiers == [STATIC_TOKEN_TIER, SERVICE_ACCOUNT_TIER]


@pytest.mark.unit
def test_auth_settings_kill_switch_returns_none_oidc_client(
    monkeypatch: "pytest.MonkeyPatch",
):
    """``disable_stored_session=True`` makes ``to_oidc_client()`` return ``None``.

    Resolver tests above already cover that ``oidc_client=None`` skips
    ``load_session``; this asserts the settings → resolver hand-off contract.
    """
    # Clear every ``PIPEFY_*`` env var so the model loads from defaults only.
    # Same pattern as ``_isolate_env`` in ``test_settings_toml_source.py``.
    import os as _os

    for key in list(_os.environ):
        if key.startswith("PIPEFY_"):
            monkeypatch.delenv(key, raising=False)

    from pipefy_infra.deployment import DeploymentConfig

    from pipefy_auth.settings import AuthConfig

    settings = AuthConfig(deployment=DeploymentConfig(), disable_stored_session=True)
    assert settings.to_oidc_client() is None


@pytest.mark.unit
def test_detect_lists_every_configured_tier_in_precedence_order(monkeypatch):
    monkeypatch.setattr(
        "pipefy_auth.resolver.load_session", lambda **_: _stored_session()
    )
    tiers = detect_pipefy_tiers(
        static_token="T",
        service_account=_service_account(),
        oidc_client=_oidc(),
    )
    assert tiers == [
        STATIC_TOKEN_TIER,
        SERVICE_ACCOUNT_TIER,
        STORED_SESSION_TIER,
    ]


@pytest.mark.unit
def test_detect_skips_tiers_without_credentials(monkeypatch):
    monkeypatch.setattr("pipefy_auth.resolver.load_session", lambda **_: None)
    tiers = detect_pipefy_tiers(static_token="T", service_account=_service_account())
    assert tiers == [STATIC_TOKEN_TIER, SERVICE_ACCOUNT_TIER]


@pytest.mark.unit
def test_missing_auth_message_mentions_all_tiers():
    msg = missing_auth_message()
    assert "PIPEFY_TOKEN" in msg
    assert "PIPEFY_SERVICE_ACCOUNT_*" in msg
    assert "pipefy auth login" in msg


@pytest.mark.unit
def test_missing_auth_message_custom_login_command():
    msg = missing_auth_message(login_command="my-cli login")
    assert "my-cli login" in msg
    assert "pipefy auth login" not in msg


@pytest.mark.unit
def test_tier_for_raises_on_foreign_auth_class():
    """``tier_for`` only recognises auth produced by ``resolve_pipefy_auth``."""

    class CustomAuth:
        pass

    with pytest.raises(ValueError, match="No resolver-tier name"):
        tier_for(CustomAuth())  # type: ignore[arg-type]


@pytest.mark.unit
def test_tier_for_recognises_callable_bearer_auth_as_stored_session():
    auth = CallableBearerAuth(lambda: "TOKEN")
    assert tier_for(auth) == STORED_SESSION_TIER


@pytest.mark.unit
def test_stored_session_provider_raises_when_session_vanishes(monkeypatch):
    """The callable provider raises if the keychain entry disappears after detect."""
    monkeypatch.setattr(
        "pipefy_auth.resolver.load_session", lambda **_: _stored_session()
    )
    monkeypatch.setattr("pipefy_auth.resolver.ensure_fresh_session", lambda **_: None)
    resolved = resolve_pipefy_auth(oidc_client=_oidc())
    assert isinstance(resolved, RefreshableBearerAuth)
    provider = resolved._token_provider  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="session was removed"):
        provider()


@pytest.mark.unit
def test_stored_session_force_refresh_calls_ensure_fresh_session_with_force(
    monkeypatch,
):
    rotated = _stored_session()
    monkeypatch.setattr("pipefy_auth.resolver.load_session", lambda **_: rotated)
    captured: dict[str, object] = {}

    def fake_ensure(**kwargs):
        captured.update(kwargs)
        return StoredSession(
            issuer=rotated.issuer,
            client_id=rotated.client_id,
            obtained_at=int(time.time()),
            token=TokenResponse(
                access_token="ROTATED",
                refresh_token="ROTATED_R",
                token_type="Bearer",
                expires_in=3600,
                refresh_expires_in=None,
                scope=None,
                id_token=None,
            ),
        )

    monkeypatch.setattr("pipefy_auth.resolver.ensure_fresh_session", fake_ensure)
    resolved = resolve_pipefy_auth(oidc_client=_oidc())
    assert isinstance(resolved, RefreshableBearerAuth)
    new_token = resolved._force_refresh()  # type: ignore[attr-defined]
    assert new_token == "ROTATED"
    assert captured.get("force") is True


@pytest.mark.unit
def test_stored_session_force_refresh_returns_none_on_refresh_error(monkeypatch):
    monkeypatch.setattr(
        "pipefy_auth.resolver.load_session", lambda **_: _stored_session()
    )

    def fake_ensure(**_: object) -> StoredSession:
        raise RefreshError("invalid_grant", error_code="invalid_grant")

    monkeypatch.setattr("pipefy_auth.resolver.ensure_fresh_session", fake_ensure)
    resolved = resolve_pipefy_auth(oidc_client=_oidc())
    assert isinstance(resolved, RefreshableBearerAuth)
    assert resolved._force_refresh() is None  # type: ignore[attr-defined]


@pytest.mark.unit
def test_stored_session_force_refresh_returns_none_when_session_vanished(monkeypatch):
    monkeypatch.setattr(
        "pipefy_auth.resolver.load_session", lambda **_: _stored_session()
    )
    monkeypatch.setattr("pipefy_auth.resolver.ensure_fresh_session", lambda **_: None)
    resolved = resolve_pipefy_auth(oidc_client=_oidc())
    assert isinstance(resolved, RefreshableBearerAuth)
    assert resolved._force_refresh() is None  # type: ignore[attr-defined]


class MockCounter:
    """Counts invocations so tests can assert short-circuit behavior."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, **_: object) -> None:
        self.calls += 1
        return None
