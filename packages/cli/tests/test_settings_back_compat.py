"""Regression: the removed ``PIPEFY_OAUTH_*`` env vars are now silently ignored.

The legacy ``PIPEFY_OAUTH_CLIENT`` / ``PIPEFY_OAUTH_SECRET`` aliases (and their
one-shot deprecation warning) were dropped. Operators must use
``PIPEFY_SERVICE_ACCOUNT_CLIENT_ID`` / ``_SECRET``; the stale names no longer
configure the service-account tier.
"""

from __future__ import annotations

import pytest

from pipefy_cli.settings import resolve_cli_settings


def test_legacy_oauth_env_vars_are_ignored(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("PIPEFY_OAUTH_CLIENT", "legacy-client")
    monkeypatch.setenv("PIPEFY_OAUTH_SECRET", "legacy-secret")

    resolved = resolve_cli_settings(
        base_url_flag=None,
        allow_insecure_urls_flag=None,
    ).auth

    # The legacy names do not populate the service-account tier, and there is
    # no deprecation warning (the shim is gone).
    assert resolved.service_account_credentials is None
    assert resolved.to_service_account() is None
    assert "deprecated" not in capsys.readouterr().err
