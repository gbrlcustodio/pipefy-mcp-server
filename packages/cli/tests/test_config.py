"""Tests for CLI configuration loading (aligned with MCP ``PIPEFY_*`` keys)."""

from __future__ import annotations

import textwrap

import pytest

from pipefy_cli.config import (
    CliSettings,
    resolve_cli_settings,
)


def test_env_only_resolution(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://env-only.example.com")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "env-client")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "env-secret")

    resolved = resolve_cli_settings(
        base_url_flag=None,
        allow_insecure_urls_flag=None,
    )

    assert resolved.sdk.base_url == "https://env-only.example.com"
    assert resolved.sdk.graphql_url == "https://env-only.example.com/graphql"
    assert resolved.sdk.internal_api_url == "https://env-only.example.com/internal_api"
    assert (
        resolved.auth.service_account_url == "https://env-only.example.com/oauth/token"
    )
    assert resolved.auth.service_account_client_id == "env-client"
    assert resolved.auth.service_account_client_secret == "env-secret"


def test_dotenv_only_resolution(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    env_file = saved_cwd / ".env"
    env_file.write_text(
        textwrap.dedent(
            """\
            PIPEFY_BASE_URL=https://dotenv.example.com
            PIPEFY_SERVICE_ACCOUNT_CLIENT_ID=dotenv-client
            PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET=dotenv-secret
            """
        ),
        encoding="utf-8",
    )

    resolved = resolve_cli_settings(
        base_url_flag=None,
        allow_insecure_urls_flag=None,
    )

    assert resolved.sdk.base_url == "https://dotenv.example.com"
    assert resolved.auth.service_account_client_id == "dotenv-client"


def test_process_env_overrides_dotenv(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    env_file = saved_cwd / ".env"
    env_file.write_text(
        "PIPEFY_BASE_URL=https://from-dotenv.example.com\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://from-process.example.com")

    resolved = resolve_cli_settings(
        base_url_flag=None,
        allow_insecure_urls_flag=None,
    ).sdk

    assert resolved.base_url == "https://from-process.example.com"


def test_base_url_flag_overrides_env(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    """``--base-url`` outranks ``PIPEFY_BASE_URL`` for both nested models."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://from-env.example.com")

    resolved = resolve_cli_settings(
        base_url_flag="https://from-flag.example.com",
        allow_insecure_urls_flag=None,
    )

    assert resolved.sdk.base_url == "https://from-flag.example.com"
    # ``AuthSettings.model_validate`` re-reads env on revalidate; without the
    # env-hold this would still report the env host and ``service_account_url``
    # would drift from the SDK side.
    assert resolved.auth.base_url == "https://from-flag.example.com"
    assert (
        resolved.auth.service_account_url == "https://from-flag.example.com/oauth/token"
    )


def test_empty_base_url_env_rejected_at_settings_load(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    """``PIPEFY_BASE_URL=""`` is rejected by pydantic ``pattern`` validation."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "")
    with pytest.raises(ValueError, match="should match pattern"):
        resolve_cli_settings(
            base_url_flag=None,
            allow_insecure_urls_flag=None,
        )


def test_base_url_defaults_to_pipefy_prod(
    clean_pipefy_env,
    saved_cwd,
):
    """No env / no flag → base_url defaults to the Pipefy production host."""
    resolved = resolve_cli_settings(
        base_url_flag=None,
        allow_insecure_urls_flag=None,
    ).sdk

    assert resolved.base_url == "https://app.pipefy.com"
    assert resolved.graphql_url == "https://app.pipefy.com/graphql"
    assert resolved.internal_api_url == "https://app.pipefy.com/internal_api"
    assert (
        resolved.interfaces_graphql_url == "https://app.pipefy.com/graphql/interfaces"
    )


def test_localhost_base_url_rejected_without_insecure_flag(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PIPEFY_ALLOW_INSECURE_URLS", "false")
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://localhost")

    with pytest.raises(ValueError, match="localhost"):
        CliSettings()


def test_allow_insecure_urls_flag_overrides_env(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PIPEFY_ALLOW_INSECURE_URLS", "false")
    monkeypatch.setenv("PIPEFY_BASE_URL", "http://127.0.0.1:9999")

    resolved = resolve_cli_settings(
        base_url_flag=None,
        allow_insecure_urls_flag=True,
    )

    assert resolved.sdk.allow_insecure_urls is True
    assert resolved.auth.allow_insecure_urls is True
    assert resolved.sdk.base_url == "http://127.0.0.1:9999"


def test_allow_insecure_urls_flag_false_overrides_env_true(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    """Flag ``False`` must override ``PIPEFY_ALLOW_INSECURE_URLS=true`` on both nested models.

    Without the env-hold for the False branch, ``AuthSettings.model_validate``
    would re-read the env and keep ``True`` while ``ClientSettings`` (a plain
    ``BaseModel``) honored the patch, desynchronizing the two SSRF gates.
    """
    monkeypatch.setenv("PIPEFY_ALLOW_INSECURE_URLS", "true")

    resolved = resolve_cli_settings(
        base_url_flag=None,
        allow_insecure_urls_flag=False,
    )

    assert resolved.sdk.allow_insecure_urls is False
    assert resolved.auth.allow_insecure_urls is False


def test_base_url_flag_localhost_rejected_without_insecure(
    clean_pipefy_env,
    saved_cwd,
):
    with pytest.raises(ValueError, match="HTTPS|http"):
        resolve_cli_settings(
            base_url_flag="http://localhost",
            allow_insecure_urls_flag=None,
        )


def test_base_url_flag_localhost_allowed_with_insecure_flag(
    clean_pipefy_env,
    saved_cwd,
):
    resolved = resolve_cli_settings(
        base_url_flag="http://localhost:3000",
        allow_insecure_urls_flag=True,
    ).sdk

    assert resolved.base_url == "http://localhost:3000"
    assert resolved.graphql_url == "http://localhost:3000/graphql"


@pytest.mark.parametrize(
    "url,allow_insecure,expect_error",
    [
        pytest.param(
            "https://signin.example.com/realms/foo",
            False,
            None,
            id="https_accepted",
        ),
        pytest.param(
            "http://signin.example.com/realms/foo",
            False,
            "HTTPS",
            id="http_rejected_strict",
        ),
        pytest.param(
            "http://localhost/realms/foo",
            True,
            None,
            id="localhost_allowed_insecure",
        ),
        pytest.param(
            "https://10.0.0.1/realms/foo",
            False,
            "private",
            id="private_ip_rejected",
        ),
    ],
)
def test_auth_url_validation(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    allow_insecure: bool,
    expect_error: str | None,
):
    monkeypatch.setenv("PIPEFY_AUTH_ISSUER_URL", url)
    if expect_error is None:
        resolved = resolve_cli_settings(
            base_url_flag=None,
            allow_insecure_urls_flag=True if allow_insecure else None,
        ).auth
        assert resolved.issuer_url == url
    else:
        with pytest.raises(ValueError, match=expect_error):
            resolve_cli_settings(
                base_url_flag=None,
                allow_insecure_urls_flag=True if allow_insecure else None,
            )
