"""Back-compat coverage for the ``PIPEFY_OAUTH_*`` → ``PIPEFY_SERVICE_ACCOUNT_*`` rename (#127).

Legacy ``PIPEFY_OAUTH_CLIENT`` / ``PIPEFY_OAUTH_SECRET`` env vars still
populate the new ``service_account_*`` fields with a one-shot stderr
deprecation warning.

The ``PIPEFY_OAUTH_URL`` legacy alias was dropped in the ``PIPEFY_BASE_URL``
rewrite — the OAuth token endpoint now derives from ``base_url``.
"""

from __future__ import annotations

import pytest
from pipefy_auth.settings import _reset_legacy_oauth_warning_state

from pipefy_cli.config import resolve_cli_settings


@pytest.fixture(autouse=True)
def _reset_warning_dedup() -> None:
    _reset_legacy_oauth_warning_state()
    yield
    _reset_legacy_oauth_warning_state()


def test_legacy_env_vars_still_populate_new_fields(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PIPEFY_OAUTH_CLIENT", "legacy-client")
    monkeypatch.setenv("PIPEFY_OAUTH_SECRET", "legacy-secret")

    resolved = resolve_cli_settings(
        base_url_flag=None,
        allow_insecure_urls_flag=None,
    ).auth

    assert resolved.service_account_client_id == "legacy-client"
    assert resolved.service_account_client_secret == "legacy-secret"


def test_new_env_var_wins_when_both_legacy_and_new_set(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PIPEFY_OAUTH_CLIENT", "legacy-client")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "new-client")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "secret")

    resolved = resolve_cli_settings(
        base_url_flag=None,
        allow_insecure_urls_flag=None,
    ).auth

    assert resolved.service_account_client_id == "new-client"


def test_legacy_env_var_emits_stderr_warning_with_new_name(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("PIPEFY_OAUTH_CLIENT", "legacy-client")

    resolve_cli_settings(
        base_url_flag=None,
        allow_insecure_urls_flag=None,
    )

    err = capsys.readouterr().err
    assert "PIPEFY_OAUTH_CLIENT is deprecated" in err
    assert "rename to PIPEFY_SERVICE_ACCOUNT_CLIENT_ID" in err
