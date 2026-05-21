"""Back-compat coverage for the env- and TOML-key rename in #127.

End-to-end: `PIPEFY_OAUTH_*` shell/.env vars and ``oauth_*`` TOML keys still
populate the new ``service_account_*`` fields, both emit one-shot stderr
deprecation warnings, and new keys win when both names are present.
"""

from __future__ import annotations

import textwrap

import pytest
from pipefy_sdk.settings import _reset_legacy_oauth_warning_state

from pipefy_cli import config as config_module
from pipefy_cli.config import (
    _reset_legacy_toml_warning_state,
    resolve_cli_settings,
)


@pytest.fixture(autouse=True)
def _reset_warning_dedup() -> None:
    _reset_legacy_oauth_warning_state()
    _reset_legacy_toml_warning_state()
    yield
    _reset_legacy_oauth_warning_state()
    _reset_legacy_toml_warning_state()


def test_legacy_env_vars_still_populate_new_fields(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PIPEFY_GRAPHQL_URL", "https://app.example.com/graphql")
    monkeypatch.setenv("PIPEFY_OAUTH_URL", "https://legacy.example.com/oauth/token")
    monkeypatch.setenv("PIPEFY_OAUTH_CLIENT", "legacy-client")
    monkeypatch.setenv("PIPEFY_OAUTH_SECRET", "legacy-secret")

    resolved = resolve_cli_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=None,
    ).pipefy

    assert resolved.service_account_url == "https://legacy.example.com/oauth/token"
    assert resolved.service_account_client_id == "legacy-client"
    assert resolved.service_account_client_secret == "legacy-secret"


def test_new_env_var_wins_when_both_legacy_and_new_set(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PIPEFY_GRAPHQL_URL", "https://app.example.com/graphql")
    monkeypatch.setenv("PIPEFY_OAUTH_URL", "https://legacy.example.com/oauth/token")
    monkeypatch.setenv(
        "PIPEFY_SERVICE_ACCOUNT_URL", "https://new.example.com/oauth/token"
    )

    resolved = resolve_cli_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=None,
    ).pipefy

    assert resolved.service_account_url == "https://new.example.com/oauth/token"


def test_legacy_env_var_emits_stderr_warning_with_new_name(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("PIPEFY_GRAPHQL_URL", "https://app.example.com/graphql")
    monkeypatch.setenv("PIPEFY_OAUTH_CLIENT", "legacy-client")

    resolve_cli_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=None,
    )

    err = capsys.readouterr().err
    assert "PIPEFY_OAUTH_CLIENT is deprecated" in err
    assert "rename to PIPEFY_SERVICE_ACCOUNT_CLIENT_ID" in err


def test_legacy_toml_keys_still_populate_new_fields(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    cfg_path = saved_cwd / "config.toml"
    cfg_path.write_text(
        textwrap.dedent(
            """\
            [pipefy]
            graphql_url = "https://app.example.com/graphql"
            oauth_url = "https://legacy-toml.example.com/oauth/token"
            oauth_client = "legacy-toml-client"
            oauth_secret = "legacy-toml-secret"
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "USER_CONFIG_PATH", cfg_path)

    resolved = resolve_cli_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=None,
    ).pipefy

    assert resolved.service_account_url == "https://legacy-toml.example.com/oauth/token"
    assert resolved.service_account_client_id == "legacy-toml-client"
    assert resolved.service_account_client_secret == "legacy-toml-secret"


def test_toml_new_key_wins_when_both_legacy_and_new_present(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    cfg_path = saved_cwd / "config.toml"
    cfg_path.write_text(
        textwrap.dedent(
            """\
            [pipefy]
            graphql_url = "https://app.example.com/graphql"
            oauth_url = "https://legacy-toml.example.com/oauth/token"
            service_account_url = "https://new-toml.example.com/oauth/token"
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "USER_CONFIG_PATH", cfg_path)

    resolved = resolve_cli_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=None,
    ).pipefy

    assert resolved.service_account_url == "https://new-toml.example.com/oauth/token"


def test_legacy_toml_key_emits_stderr_warning_with_new_name(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    cfg_path = saved_cwd / "config.toml"
    cfg_path.write_text(
        textwrap.dedent(
            """\
            [pipefy]
            graphql_url = "https://app.example.com/graphql"
            oauth_secret = "legacy-toml-secret"
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "USER_CONFIG_PATH", cfg_path)

    resolve_cli_settings(
        graphql_url_flag=None,
        allow_insecure_urls_flag=None,
    )

    err = capsys.readouterr().err
    assert "'oauth_secret'" in err
    assert "is deprecated" in err
    assert "'service_account_client_secret'" in err


def test_toml_warning_dedups_across_repeated_loads(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    cfg_path = saved_cwd / "config.toml"
    cfg_path.write_text(
        textwrap.dedent(
            """\
            [pipefy]
            graphql_url = "https://app.example.com/graphql"
            oauth_url = "https://legacy-toml.example.com/oauth/token"
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "USER_CONFIG_PATH", cfg_path)

    for _ in range(3):
        resolve_cli_settings(
            graphql_url_flag=None,
            allow_insecure_urls_flag=None,
        )

    err = capsys.readouterr().err
    assert err.count("'oauth_url' in") == 1
