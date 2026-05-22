"""Tests for CLI configuration loading (aligned with MCP ``PIPEFY_*`` keys)."""

from __future__ import annotations

import textwrap

import pytest

from pipefy_cli import config as config_module
from pipefy_cli.config import (
    CliSettings,
    apply_toml_fallback,
    ensure_public_graphql_configured,
    resolve_cli_settings,
)


def test_env_only_resolution(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(
        "PIPEFY_GRAPHQL_URL",
        "https://env-only.example.com/graphql",
    )
    monkeypatch.setenv(
        "PIPEFY_INTERNAL_API_URL",
        "https://env-only.example.com/internal_api",
    )
    monkeypatch.setenv(
        "PIPEFY_SERVICE_ACCOUNT_URL", "https://env-only.example.com/oauth/token"
    )
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "env-client")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "env-secret")

    resolved = resolve_cli_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=None,
    ).pipefy

    assert resolved.graphql_url == "https://env-only.example.com/graphql"
    assert resolved.internal_api_url == "https://env-only.example.com/internal_api"
    assert resolved.service_account_url == "https://env-only.example.com/oauth/token"
    assert resolved.service_account_client_id == "env-client"
    assert resolved.service_account_client_secret == "env-secret"


def test_dotenv_only_resolution(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    env_file = saved_cwd / ".env"
    env_file.write_text(
        textwrap.dedent(
            """\
            PIPEFY_GRAPHQL_URL=https://dotenv.example.com/graphql
            PIPEFY_INTERNAL_API_URL=https://dotenv.example.com/internal_api
            PIPEFY_SERVICE_ACCOUNT_URL=https://dotenv.example.com/oauth/token
            PIPEFY_SERVICE_ACCOUNT_CLIENT_ID=dotenv-client
            PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET=dotenv-secret
            """
        ),
        encoding="utf-8",
    )

    resolved = resolve_cli_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=None,
    ).pipefy

    assert resolved.graphql_url == "https://dotenv.example.com/graphql"
    assert resolved.service_account_client_id == "dotenv-client"


def test_process_env_overrides_dotenv(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    env_file = saved_cwd / ".env"
    env_file.write_text(
        "PIPEFY_GRAPHQL_URL=https://from-dotenv.example.com/graphql\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "PIPEFY_GRAPHQL_URL",
        "https://from-process.example.com/graphql",
    )

    resolved = resolve_cli_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=None,
    ).pipefy

    assert resolved.graphql_url == "https://from-process.example.com/graphql"


def test_graphql_url_flag_overrides_env(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(
        "PIPEFY_GRAPHQL_URL",
        "https://from-env.example.com/graphql",
    )

    resolved = resolve_cli_settings(
        graphql_url_flag="https://from-flag.example.com/graphql",
        allow_insecure_urls_flag=None,
    ).pipefy

    assert resolved.graphql_url == "https://from-flag.example.com/graphql"


def test_missing_graphql_url_error_points_to_setup_docs(
    clean_pipefy_env,
    saved_cwd,
):
    resolved = resolve_cli_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=None,
    ).pipefy

    with pytest.raises(ValueError, match="docs/setup\\.md"):
        ensure_public_graphql_configured(resolved)


def test_localhost_graphql_rejected_without_insecure_flag(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PIPEFY_ALLOW_INSECURE_URLS", "false")
    monkeypatch.setenv("PIPEFY_GRAPHQL_URL", "https://localhost/graphql")

    with pytest.raises(ValueError, match="localhost"):
        CliSettings()


def test_allow_insecure_urls_flag_overrides_env(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PIPEFY_ALLOW_INSECURE_URLS", "false")
    monkeypatch.setenv("PIPEFY_GRAPHQL_URL", "http://127.0.0.1:9999/graphql")

    resolved = resolve_cli_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=True,
    ).pipefy

    assert resolved.allow_insecure_urls is True
    assert resolved.graphql_url == "http://127.0.0.1:9999/graphql"


def test_user_toml_fallback_lowest_precedence(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    cfg_path = saved_cwd / "config.toml"
    cfg_path.write_text(
        textwrap.dedent(
            """\
            [pipefy]
            graphql_url = "https://from-toml.example.com/graphql"
            service_account_client_id = "toml-client"
            service_account_client_secret = "toml-secret"
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "USER_CONFIG_PATH", cfg_path)

    resolved = resolve_cli_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=None,
    ).pipefy

    assert resolved.graphql_url == "https://from-toml.example.com/graphql"
    assert resolved.service_account_client_id == "toml-client"


def test_env_overrides_user_toml(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    cfg_path = saved_cwd / "config.toml"
    cfg_path.write_text(
        textwrap.dedent(
            """\
            [pipefy]
            graphql_url = "https://from-toml.example.com/graphql"
            service_account_client_id = "toml-client"
            service_account_client_secret = "toml-secret"
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "USER_CONFIG_PATH", cfg_path)
    monkeypatch.setenv(
        "PIPEFY_GRAPHQL_URL",
        "https://from-env.example.com/graphql",
    )

    resolved = resolve_cli_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=None,
    ).pipefy

    assert resolved.graphql_url == "https://from-env.example.com/graphql"


def test_apply_toml_fills_only_missing_fields(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    from pipefy_sdk import PipefySettings

    cfg_path = saved_cwd / "config.toml"
    cfg_path.write_text(
        textwrap.dedent(
            """\
            [pipefy]
            graphql_url = "https://toml-only.example.com/graphql"
            service_account_client_id = "toml-client"
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "USER_CONFIG_PATH", cfg_path)

    base = PipefySettings(service_account_client_id="from-env")
    merged = apply_toml_fallback(base)

    assert merged.graphql_url == "https://toml-only.example.com/graphql"
    assert merged.service_account_client_id == "from-env"


def test_graphql_url_flag_localhost_rejected_without_insecure(
    clean_pipefy_env,
    saved_cwd,
):
    with pytest.raises(ValueError, match="HTTPS|http"):
        resolve_cli_settings(
            graphql_url_flag="http://localhost/graphql",
            allow_insecure_urls_flag=None,
        )


def test_graphql_url_flag_localhost_allowed_with_insecure_flag(
    clean_pipefy_env,
    saved_cwd,
):
    resolved = resolve_cli_settings(
        graphql_url_flag="http://localhost/graphql",
        allow_insecure_urls_flag=True,
    ).pipefy
    assert resolved.graphql_url == "http://localhost/graphql"
    assert resolved.allow_insecure_urls is True


def test_toml_private_graphql_url_rejected(clean_pipefy_env, saved_cwd, monkeypatch):
    cfg_path = saved_cwd / "config.toml"
    cfg_path.write_text(
        textwrap.dedent(
            """\
            [pipefy]
            graphql_url = "http://10.0.0.1/graphql"
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "USER_CONFIG_PATH", cfg_path)

    with pytest.raises(ValueError):
        resolve_cli_settings(
            graphql_url_flag=None,
            allow_insecure_urls_flag=None,
        )


def test_corrupt_user_config_toml_raises_actionable_error(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch,
):
    cfg_path = saved_cwd / "config.toml"
    cfg_path.write_text("[pipefy\ngraphql_url = ", encoding="utf-8")
    monkeypatch.setattr(config_module, "USER_CONFIG_PATH", cfg_path)

    with pytest.raises(ValueError, match="docs/setup"):
        resolve_cli_settings(
            graphql_url_flag=None,
            allow_insecure_urls_flag=None,
        )


@pytest.mark.parametrize(
    ("url", "allow_insecure_flag", "should_reject"),
    [
        ("https://signin.example.com/realms/pipefy", None, False),
        ("http://signin.example.com/realms/pipefy", None, True),
        ("http://localhost:8080/realms/dev", True, False),
        ("https://10.0.0.1/realms/pipefy", None, True),
    ],
    ids=[
        "https_accepted",
        "http_rejected_strict",
        "localhost_allowed_insecure",
        "private_ip_rejected",
    ],
)
def test_auth_url_validation(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    allow_insecure_flag: bool | None,
    should_reject: bool,
):
    monkeypatch.setenv("PIPEFY_AUTH_URL", url)
    if should_reject:
        with pytest.raises(ValueError, match="auth_url"):
            resolve_cli_settings(
                graphql_url_flag=None,
                allow_insecure_urls_flag=allow_insecure_flag,
            )
    else:
        resolved = resolve_cli_settings(
            graphql_url_flag=None,
            allow_insecure_urls_flag=allow_insecure_flag,
        )
        assert resolved.auth_url == url
