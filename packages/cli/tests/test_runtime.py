"""Tests for the CLI composition root (resolve_cli_runtime -> CliRuntime)."""

from __future__ import annotations

import textwrap

import pytest

from pipefy_cli.runtime import resolve_cli_runtime


def _resolve(**kw):
    kw.setdefault("base_url_flag", None)
    kw.setdefault("allow_insecure_urls_flag", None)
    kw.setdefault("token_flag", None)
    return resolve_cli_runtime(**kw)


def test_env_only_resolution(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://env-only.example.com")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "env-client")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "env-secret")

    runtime = _resolve()

    assert runtime.endpoints.graphql_url == "https://env-only.example.com/graphql"
    assert (
        runtime.endpoints.internal_api_url
        == "https://env-only.example.com/internal_api"
    )
    sa = runtime.credentials.service_account
    assert sa is not None
    assert sa.token_url == "https://env-only.example.com/oauth/token"
    assert sa.client_id == "env-client"
    assert sa.client_secret == "env-secret"


def test_endpoints_and_token_url_share_one_host(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    """The SDK endpoints and the service-account token URL derive from one host.

    Structurally guaranteed: resolve_cli_runtime builds ONE DeploymentConfig and
    feeds it to both loaders, so the endpoints and the OAuth token URL cannot
    drift onto different hosts.
    """
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://shared.example.com")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "sec")
    runtime = _resolve()
    assert runtime.endpoints.graphql_url == "https://shared.example.com/graphql"
    assert runtime.credentials.service_account.token_url == (
        "https://shared.example.com/oauth/token"
    )


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

    runtime = _resolve()

    assert runtime.endpoints.graphql_url == "https://dotenv.example.com/graphql"
    assert runtime.credentials.service_account.client_id == "dotenv-client"


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

    runtime = _resolve()

    assert runtime.endpoints.graphql_url == "https://from-process.example.com/graphql"


def test_base_url_flag_overrides_env(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    """``--base-url`` outranks ``PIPEFY_BASE_URL`` for the one shared deployment."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://from-env.example.com")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "sec")

    runtime = _resolve(base_url_flag="https://from-flag.example.com")

    assert runtime.endpoints.graphql_url == "https://from-flag.example.com/graphql"
    assert runtime.credentials.service_account.token_url == (
        "https://from-flag.example.com/oauth/token"
    )


def test_empty_base_url_env_rejected_at_runtime_load(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    """``PIPEFY_BASE_URL=""`` is rejected by pydantic ``pattern`` validation."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "")
    with pytest.raises(ValueError, match="should match pattern"):
        _resolve()


def test_base_url_defaults_to_pipefy_prod(clean_pipefy_env, saved_cwd):
    """No env / no flag -> endpoints derive from the Pipefy production host."""
    runtime = _resolve()
    assert runtime.endpoints.graphql_url == "https://app.pipefy.com/graphql"
    assert runtime.endpoints.internal_api_url == "https://app.pipefy.com/internal_api"
    assert (
        runtime.endpoints.interfaces_graphql_url
        == "https://app.pipefy.com/graphql/interfaces"
    )


def test_localhost_base_url_rejected_without_insecure_flag(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PIPEFY_ALLOW_INSECURE_URLS", "false")
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://localhost")

    with pytest.raises(ValueError, match="localhost"):
        _resolve()


def test_allow_insecure_urls_flag_overrides_env(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PIPEFY_ALLOW_INSECURE_URLS", "false")
    monkeypatch.setenv("PIPEFY_BASE_URL", "http://127.0.0.1:9999")

    runtime = _resolve(allow_insecure_urls_flag=True)

    assert runtime.allow_insecure_urls is True
    assert runtime.endpoints.graphql_url == "http://127.0.0.1:9999/graphql"


def test_allow_insecure_urls_flag_false_overrides_env_true(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    """Flag ``False`` must override ``PIPEFY_ALLOW_INSECURE_URLS=true`` deployment-wide."""
    monkeypatch.setenv("PIPEFY_ALLOW_INSECURE_URLS", "true")

    runtime = _resolve(allow_insecure_urls_flag=False)

    assert runtime.allow_insecure_urls is False


def test_base_url_flag_localhost_rejected_without_insecure(clean_pipefy_env, saved_cwd):
    with pytest.raises(ValueError, match="HTTPS|http"):
        _resolve(base_url_flag="http://localhost")


def test_base_url_flag_localhost_allowed_with_insecure_flag(
    clean_pipefy_env, saved_cwd
):
    runtime = _resolve(
        base_url_flag="http://localhost:3000", allow_insecure_urls_flag=True
    )
    assert runtime.endpoints.graphql_url == "http://localhost:3000/graphql"


def test_token_flag_overrides_env_and_records_source(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PIPEFY_TOKEN", "env-token")
    runtime = _resolve(token_flag="flag-token")
    assert runtime.credentials.static_token == "flag-token"
    assert runtime.token_source == "flag"


def test_env_token_records_env_source(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PIPEFY_TOKEN", "env-token")
    runtime = _resolve()
    assert runtime.credentials.static_token == "env-token"
    assert runtime.token_source == "env"


def test_org_id_resolves_at_the_cli_edge(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
):
    """``PIPEFY_ORG_ID`` is a CLI-only edge value, exposed on CliRuntime."""
    monkeypatch.setenv("PIPEFY_ORG_ID", "300123")
    assert _resolve().org_id == "300123"


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
def test_issuer_url_validation(
    clean_pipefy_env,
    saved_cwd,
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    allow_insecure: bool,
    expect_error: str | None,
):
    monkeypatch.setenv("PIPEFY_AUTH_ISSUER_URL", url)
    flag = True if allow_insecure else None
    if expect_error is None:
        runtime = _resolve(allow_insecure_urls_flag=flag)
        assert runtime.credentials.oidc_client.issuer_url == url
    else:
        with pytest.raises(ValueError, match=expect_error):
            _resolve(allow_insecure_urls_flag=flag)
