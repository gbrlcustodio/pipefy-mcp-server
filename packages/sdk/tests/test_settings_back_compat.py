"""Back-compat coverage for the ``PIPEFY_OAUTH_*`` → ``PIPEFY_SERVICE_ACCOUNT_*`` rename.

The rename ships an ``AliasChoices`` shim on ``PipefySettings`` plus a one-shot
stderr deprecation warning. These tests pin both behaviors so the eventual
PR that drops the aliases (and the warning) has a clear regression surface.
"""

from __future__ import annotations

import pytest

from pipefy_sdk.settings import (
    _LEGACY_ENV_KEYS_TO_NEW,
    PipefySettings,
    _reset_legacy_oauth_warning_state,
    _warn_once_for_legacy_oauth_env_keys,
)


@pytest.fixture(autouse=True)
def _reset_warning_dedup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test sees a fresh warning dedup set and a clean process env."""
    for key in _LEGACY_ENV_KEYS_TO_NEW:
        monkeypatch.delenv(key, raising=False)
    for key in _LEGACY_ENV_KEYS_TO_NEW.values():
        monkeypatch.delenv(key, raising=False)
    _reset_legacy_oauth_warning_state()
    yield
    _reset_legacy_oauth_warning_state()


@pytest.mark.unit
def test_legacy_kwargs_populate_new_fields():
    """``PipefySettings(oauth_url=...)`` still validates and binds to ``service_account_url``."""
    s = PipefySettings(
        graphql_url="https://app.pipefy.com/graphql",
        oauth_url="https://legacy.example.com/oauth/token",
        oauth_client="legacy-client",
        oauth_secret="legacy-secret",
    )
    assert s.service_account_url == "https://legacy.example.com/oauth/token"
    assert s.service_account_client_id == "legacy-client"
    assert s.service_account_client_secret == "legacy-secret"


@pytest.mark.unit
def test_new_kwargs_populate_new_fields():
    s = PipefySettings(
        graphql_url="https://app.pipefy.com/graphql",
        service_account_url="https://new.example.com/oauth/token",
        service_account_client_id="new-client",
        service_account_client_secret="new-secret",
    )
    assert s.service_account_url == "https://new.example.com/oauth/token"
    assert s.service_account_client_id == "new-client"
    assert s.service_account_client_secret == "new-secret"


@pytest.mark.unit
def test_legacy_env_var_emits_deprecation_warning(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("PIPEFY_OAUTH_URL", "https://shell.example.com/oauth/token")

    # Trigger via direct emitter call — model construction below would also trigger,
    # but the emitter is the unit under test here.
    _warn_once_for_legacy_oauth_env_keys()

    err = capsys.readouterr().err
    assert "PIPEFY_OAUTH_URL is deprecated" in err
    assert "rename to PIPEFY_SERVICE_ACCOUNT_URL" in err
    # Only the legacy key that is set should warn.
    assert "PIPEFY_OAUTH_CLIENT" not in err
    assert "PIPEFY_OAUTH_SECRET" not in err


@pytest.mark.unit
def test_deprecation_warning_dedups_within_process(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("PIPEFY_OAUTH_URL", "https://shell.example.com/oauth/token")

    _warn_once_for_legacy_oauth_env_keys()
    _warn_once_for_legacy_oauth_env_keys()
    _warn_once_for_legacy_oauth_env_keys()

    err = capsys.readouterr().err
    assert err.count("PIPEFY_OAUTH_URL is deprecated") == 1


@pytest.mark.unit
def test_no_deprecation_warning_when_only_new_env_keys_set(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv(
        "PIPEFY_SERVICE_ACCOUNT_URL", "https://new.example.com/oauth/token"
    )
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "new-client")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "new-secret")

    PipefySettings(
        graphql_url="https://app.pipefy.com/graphql",
        service_account_url="https://new.example.com/oauth/token",
        service_account_client_id="new-client",
        service_account_client_secret="new-secret",
    )

    err = capsys.readouterr().err
    assert "deprecated" not in err


@pytest.mark.unit
def test_pipefy_settings_construction_triggers_warning_via_model_validator(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """The ``mode="before"`` model_validator wires the warning into PipefySettings init."""
    monkeypatch.setenv("PIPEFY_OAUTH_SECRET", "legacy-secret-in-shell")

    PipefySettings(graphql_url="https://app.pipefy.com/graphql")

    err = capsys.readouterr().err
    assert "PIPEFY_OAUTH_SECRET is deprecated" in err
    assert "rename to PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET" in err
