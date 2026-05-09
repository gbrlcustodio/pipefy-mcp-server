"""Tests for CLI configuration loading (aligned with MCP ``PIPEFY_*`` keys)."""

from __future__ import annotations

import textwrap

import pytest

from pipefy_cli import config as config_module
from pipefy_cli.config import (
    CliSettings,
    apply_toml_fallback,
    ensure_public_graphql_configured,
    resolve_pipefy_settings,
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
    monkeypatch.setenv("PIPEFY_OAUTH_URL", "https://env-only.example.com/oauth/token")
    monkeypatch.setenv("PIPEFY_OAUTH_CLIENT", "env-client")
    monkeypatch.setenv("PIPEFY_OAUTH_SECRET", "env-secret")

    resolved = resolve_pipefy_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=None,
    )

    assert resolved.graphql_url == "https://env-only.example.com/graphql"
    assert resolved.internal_api_url == "https://env-only.example.com/internal_api"
    assert resolved.oauth_url == "https://env-only.example.com/oauth/token"
    assert resolved.oauth_client == "env-client"
    assert resolved.oauth_secret == "env-secret"


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
            PIPEFY_OAUTH_URL=https://dotenv.example.com/oauth/token
            PIPEFY_OAUTH_CLIENT=dotenv-client
            PIPEFY_OAUTH_SECRET=dotenv-secret
            """
        ),
        encoding="utf-8",
    )

    resolved = resolve_pipefy_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=None,
    )

    assert resolved.graphql_url == "https://dotenv.example.com/graphql"
    assert resolved.oauth_client == "dotenv-client"


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

    resolved = resolve_pipefy_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=None,
    )

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

    resolved = resolve_pipefy_settings(
        graphql_url_flag="https://from-flag.example.com/graphql",
        allow_insecure_urls_flag=None,
    )

    assert resolved.graphql_url == "https://from-flag.example.com/graphql"


def test_missing_graphql_url_error_points_to_setup_docs(
    clean_pipefy_env,
    saved_cwd,
):
    resolved = resolve_pipefy_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=None,
    )

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

    resolved = resolve_pipefy_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=True,
    )

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
            oauth_client = "toml-client"
            oauth_secret = "toml-secret"
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "USER_CONFIG_PATH", cfg_path)

    resolved = resolve_pipefy_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=None,
    )

    assert resolved.graphql_url == "https://from-toml.example.com/graphql"
    assert resolved.oauth_client == "toml-client"


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
            oauth_client = "toml-client"
            oauth_secret = "toml-secret"
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "USER_CONFIG_PATH", cfg_path)
    monkeypatch.setenv(
        "PIPEFY_GRAPHQL_URL",
        "https://from-env.example.com/graphql",
    )

    resolved = resolve_pipefy_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=None,
    )

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
            oauth_client = "toml-client"
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "USER_CONFIG_PATH", cfg_path)

    base = PipefySettings(oauth_client="from-env")
    merged = apply_toml_fallback(base)

    assert merged.graphql_url == "https://toml-only.example.com/graphql"
    assert merged.oauth_client == "from-env"
