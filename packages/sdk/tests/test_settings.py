"""Unit tests for ``ClientSettings`` as a pure value object.

``ClientSettings`` reads no env / ``.env`` / TOML; the application edge builds it
from :func:`pipefy_infra.config.read_client_env` (or explicit kwargs). These
tests construct it directly with keyword args and assert its self-validation:
defaults, the computed URL derivations, ``base_url`` whitespace strip, and the
SSRF / shape gate. The env / ``.env`` /
TOML plumbing is the reader's concern; see ``test_settings_toml_source.py``
(SDK end-to-end) and ``packages/infra/tests/test_edge_readers.py``.

The removed ``org_id`` field moved to the CLI composite
(``packages/cli/tests/test_config.py``); ``permission_denied_enrichment_timeout_seconds``
moved to ``McpSettings`` (the MCP tests).
"""

from __future__ import annotations

import pytest

from pipefy_sdk.settings import DEFAULT_BASE_URL, ClientSettings

PROD_GRAPHQL_URL = "https://app.pipefy.com/graphql"
PROD_INTERNAL_API_URL = "https://app.pipefy.com/internal_api"
PROD_INTERFACES_GRAPHQL_URL = "https://app.pipefy.com/graphql/interfaces"
PROD_OAUTH_TOKEN_URL = "https://app.pipefy.com/oauth/token"


@pytest.mark.unit
def test_pipefy_settings_default_base_url():
    """No kwarg → base_url defaults to the Pipefy prod API host."""
    settings = ClientSettings()
    assert settings.base_url == DEFAULT_BASE_URL == "https://app.pipefy.com"


@pytest.mark.unit
def test_pipefy_settings_default_derives_prod_urls():
    """All computed URLs follow the default base_url."""
    settings = ClientSettings()
    assert settings.graphql_url == PROD_GRAPHQL_URL
    assert settings.internal_api_url == PROD_INTERNAL_API_URL
    assert settings.interfaces_graphql_url == PROD_INTERFACES_GRAPHQL_URL
    assert settings.oauth_token_url == PROD_OAUTH_TOKEN_URL


@pytest.mark.unit
def test_pipefy_settings_base_url_drives_derived_urls():
    """``base_url`` flows into every computed URL."""
    settings = ClientSettings(base_url="https://staging.example.com")
    assert settings.base_url == "https://staging.example.com"
    assert settings.graphql_url == "https://staging.example.com/graphql"
    assert settings.internal_api_url == "https://staging.example.com/internal_api"
    assert (
        settings.interfaces_graphql_url
        == "https://staging.example.com/graphql/interfaces"
    )
    assert settings.oauth_token_url == "https://staging.example.com/oauth/token"


@pytest.mark.unit
def test_pipefy_settings_trailing_slash_on_base_does_not_double():
    """A trailing slash on ``base_url`` doesn't double the joiner."""
    settings = ClientSettings(base_url="https://staging.example.com/")
    assert settings.graphql_url == "https://staging.example.com/graphql"
    assert settings.oauth_token_url == "https://staging.example.com/oauth/token"


@pytest.mark.unit
def test_pipefy_settings_empty_base_url_raises():
    """Empty base_url is rejected by the shape pattern at construction."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="should match pattern"):
        ClientSettings(base_url="")


@pytest.mark.unit
def test_pipefy_settings_rejects_http_base_url():
    """``base_url`` must use HTTPS unless ``allow_insecure_urls``."""
    with pytest.raises(ValueError, match="base_url.*HTTPS"):
        ClientSettings(base_url="http://app.pipefy.com")


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
        ClientSettings(base_url=unsafe_base_url)


@pytest.mark.unit
def test_pipefy_settings_accepts_http_base_url_when_insecure():
    """``allow_insecure_urls=True`` opens the door to http:// + localhost."""
    settings = ClientSettings(
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
def test_pipefy_settings_base_url_accepts_uppercase_scheme(scheme_case: str):
    """RFC 3986 §3.1: URL scheme is case-insensitive."""
    url = f"{scheme_case}://app.pipefy.com"
    settings = ClientSettings(base_url=url, allow_insecure_urls=True)
    assert settings.base_url == url


@pytest.mark.unit
def test_pipefy_settings_base_url_strips_surrounding_whitespace():
    """Operator copy-paste sometimes carries leading/trailing whitespace; strip before pattern."""
    settings = ClientSettings(base_url="  https://app.pipefy.com\t")
    assert settings.base_url == "https://app.pipefy.com"
