"""Unit tests for ``PipefySettings`` (defaults, env loading, SSRF validation)."""

from __future__ import annotations

import pytest
from _shared.live_settings import live_pipefy_settings

from pipefy_sdk.settings import DEFAULT_BASE_URL, PipefySettings

PROD_GRAPHQL_URL = "https://app.pipefy.com/graphql"
PROD_INTERNAL_API_URL = "https://app.pipefy.com/internal_api"
PROD_INTERFACES_GRAPHQL_URL = "https://app.pipefy.com/graphql/interfaces"


@pytest.mark.unit
def test_pipefy_settings_default_base_url():
    """No env / kwarg → base_url defaults to the Pipefy prod API host."""
    settings = PipefySettings()
    assert settings.base_url == DEFAULT_BASE_URL == "https://app.pipefy.com"


@pytest.mark.unit
def test_pipefy_settings_default_derives_prod_urls():
    """All three computed URLs follow the default base_url."""
    settings = PipefySettings()
    assert settings.graphql_url == PROD_GRAPHQL_URL
    assert settings.internal_api_url == PROD_INTERNAL_API_URL
    assert settings.interfaces_graphql_url == PROD_INTERFACES_GRAPHQL_URL


@pytest.mark.unit
def test_pipefy_settings_base_url_env_drives_derived_urls(
    monkeypatch: pytest.MonkeyPatch,
):
    """``PIPEFY_BASE_URL`` flows into all three computed URLs."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://staging.example.com")
    settings = live_pipefy_settings()
    assert settings.base_url == "https://staging.example.com"
    assert settings.graphql_url == "https://staging.example.com/graphql"
    assert settings.internal_api_url == "https://staging.example.com/internal_api"
    assert (
        settings.interfaces_graphql_url
        == "https://staging.example.com/graphql/interfaces"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "legacy_env_var",
    [
        "PIPEFY_GRAPHQL_URL",
        "PIPEFY_INTERNAL_API_URL",
        "PIPEFY_INTERFACES_GRAPHQL_URL",
        "PIPEFY_SERVICE_ACCOUNT_URL",
    ],
)
def test_pipefy_settings_ignores_removed_per_url_env_vars(
    monkeypatch: pytest.MonkeyPatch, legacy_env_var: str
):
    """Per-URL env vars from earlier betas are silently ignored (``extra="ignore"``).

    Locks the hard break: setting any of them must not steer the computed URLs
    off the prod default. Operators have to migrate to ``PIPEFY_BASE_URL``.
    """
    monkeypatch.setenv(legacy_env_var, "https://stale.example.com/whatever")
    settings = live_pipefy_settings()
    assert settings.base_url == DEFAULT_BASE_URL
    assert settings.graphql_url == PROD_GRAPHQL_URL
    assert settings.internal_api_url == PROD_INTERNAL_API_URL
    assert settings.interfaces_graphql_url == PROD_INTERFACES_GRAPHQL_URL


@pytest.mark.unit
def test_pipefy_settings_trailing_slash_on_base_does_not_double(
    monkeypatch: pytest.MonkeyPatch,
):
    """A trailing slash on ``PIPEFY_BASE_URL`` doesn't double the joiner."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://staging.example.com/")
    settings = live_pipefy_settings()
    assert settings.graphql_url == "https://staging.example.com/graphql"


@pytest.mark.unit
def test_pipefy_settings_empty_base_url_raises(monkeypatch: pytest.MonkeyPatch):
    """Empty PIPEFY_BASE_URL is rejected at construction (no opt-out overload)."""
    from pydantic import ValidationError

    monkeypatch.setenv("PIPEFY_BASE_URL", "")
    with pytest.raises(ValidationError, match="should match pattern"):
        live_pipefy_settings()


@pytest.mark.unit
def test_pipefy_settings_rejects_http_base_url():
    """``base_url`` must use HTTPS unless ``allow_insecure_urls``."""
    with pytest.raises(ValueError, match="base_url.*HTTPS"):
        PipefySettings(base_url="http://app.pipefy.com")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("unsafe_base_url", "expected"),
    [
        ("https://localhost", "localhost"),
        ("https://10.0.0.1", "private|loopback|link-local"),
    ],
)
def test_pipefy_settings_rejects_internal_hosts(unsafe_base_url: str, expected: str):
    """SSRF guard: HTTPS URLs aimed at internal hosts are rejected at construction.

    The derived ``graphql_url`` / ``internal_api_url`` / ``interfaces_graphql_url``
    inherit this host, so validating ``base_url`` once is the single gate; the
    endpoint clients trust it rather than re-checking.
    """
    with pytest.raises(ValueError, match=expected):
        PipefySettings(base_url=unsafe_base_url)


@pytest.mark.unit
def test_pipefy_settings_accepts_http_base_url_when_insecure():
    """`allow_insecure_urls=True` opens the door to http:// + localhost."""
    settings = PipefySettings(
        base_url="http://localhost:3000",
        allow_insecure_urls=True,
    )
    assert settings.base_url == "http://localhost:3000"
    assert settings.graphql_url == "http://localhost:3000/graphql"


@pytest.mark.unit
@pytest.mark.parametrize(
    "scheme_case",
    ["HTTPS", "Https", "hTtPs", "HTTP"],
)
def test_pipefy_settings_base_url_accepts_uppercase_scheme(
    monkeypatch: pytest.MonkeyPatch, scheme_case: str
):
    """RFC 3986 §3.1: URL scheme is case-insensitive."""
    monkeypatch.setenv("PIPEFY_ALLOW_INSECURE_URLS", "true")
    url = f"{scheme_case}://app.pipefy.com"
    monkeypatch.setenv("PIPEFY_BASE_URL", url)
    settings = live_pipefy_settings()
    assert settings.base_url == url


@pytest.mark.unit
def test_pipefy_settings_base_url_strips_surrounding_whitespace(
    monkeypatch: pytest.MonkeyPatch,
):
    """Operator copy-paste sometimes carries leading/trailing whitespace — strip before pattern."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "  https://app.pipefy.com\t")
    settings = live_pipefy_settings()
    assert settings.base_url == "https://app.pipefy.com"


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_org_id",
    [
        "not-a-number",
        "١٢٣",  # Arabic-Indic digits — Unicode \d would accept, [0-9] rejects
        "१२३",  # Devanagari digits
        "1.2",
        "-123",
    ],
)
def test_pipefy_settings_org_id_rejects_non_ascii_numeric(
    monkeypatch: pytest.MonkeyPatch, bad_org_id: str
):
    from pydantic import ValidationError

    monkeypatch.setenv("PIPEFY_ORG_ID", bad_org_id)
    with pytest.raises(ValidationError, match="should match pattern"):
        live_pipefy_settings()
