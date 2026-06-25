"""Env-var resolution and normalization for the renamed ``PIPEFY_AUTH_*`` knobs.

Covers the issuer default and its env override, the ``disable_stored_session``
kill-switch, and ``keychain_backend`` normalization / validation. These pin the
env-var names and value handling after the ``PIPEFY_AUTH_`` prefix rename.
"""

from __future__ import annotations

import pytest

from pipefy_auth.settings import AuthSettings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test sees a clean process env for the vars it exercises."""
    monkeypatch.delenv("PIPEFY_SERVICE_ACCOUNT_URL", raising=False)
    monkeypatch.delenv("PIPEFY_BASE_URL", raising=False)
    monkeypatch.delenv("PIPEFY_AUTH_ISSUER_URL", raising=False)
    monkeypatch.delenv("PIPEFY_AUTH_DISABLE_STORED_SESSION", raising=False)
    monkeypatch.delenv("PIPEFY_AUTH_KEYCHAIN_BACKEND", raising=False)


@pytest.mark.unit
def test_bare_name_env_vars_do_not_leak_into_auth_settings(
    monkeypatch: pytest.MonkeyPatch,
):
    """Unprefixed env vars (``BASE_URL``, ``STATIC_TOKEN``, ...) must not be honored.

    pydantic-settings env loading is case-insensitive by default, so an
    unprefixed alias on ``AliasChoices`` would let any bare-name env var
    on the host bleed into Pipefy auth settings, an auth-redirect /
    credential-leak primitive.
    """
    monkeypatch.setenv("BASE_URL", "https://evil.example.com")
    monkeypatch.setenv("STATIC_TOKEN", "leaked")
    monkeypatch.setenv("ALLOW_INSECURE_URLS", "true")
    settings = AuthSettings()
    assert settings.base_url == "https://app.pipefy.com"  # default, not leaked
    assert settings.static_token is None
    assert settings.allow_insecure_urls is False


@pytest.mark.unit
def test_base_url_defaults_to_prod():
    """``AuthSettings()`` with no env defaults to the Pipefy prod API host."""
    settings = AuthSettings()
    assert settings.base_url == "https://app.pipefy.com"
    assert settings.service_account_url == "https://app.pipefy.com/oauth/token"


@pytest.mark.unit
def test_issuer_url_defaults_to_pipefy_prod_idp():
    """``AuthSettings()`` with no env defaults to the Pipefy prod IdP."""
    settings = AuthSettings()
    assert settings.issuer_url == "https://signin.pipefy.com/realms/pipefy"
    oidc = settings.to_oidc_client()
    assert oidc.issuer_url == "https://signin.pipefy.com/realms/pipefy"


@pytest.mark.unit
def test_pipefy_base_url_env_drives_service_account_url(
    monkeypatch: pytest.MonkeyPatch,
):
    """``PIPEFY_BASE_URL`` flows into the ``service_account_url`` computed field."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://staging.example.com")
    settings = AuthSettings()
    assert settings.base_url == "https://staging.example.com"
    assert settings.service_account_url == "https://staging.example.com/oauth/token"


@pytest.mark.unit
def test_pipefy_auth_issuer_url_env_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
):
    """``PIPEFY_AUTH_ISSUER_URL`` overrides the default issuer URL."""
    monkeypatch.setenv("PIPEFY_AUTH_ISSUER_URL", "https://other.example.com/realms/x")
    settings = AuthSettings()
    assert settings.issuer_url == "https://other.example.com/realms/x"


@pytest.mark.unit
@pytest.mark.parametrize(
    "env_key",
    ["PIPEFY_BASE_URL", "PIPEFY_AUTH_ISSUER_URL"],
)
def test_empty_url_env_raises(monkeypatch: pytest.MonkeyPatch, env_key: str):
    """Empty URL env values are rejected at construction (no opt-out overload)."""
    from pydantic import ValidationError

    monkeypatch.setenv(env_key, "")
    with pytest.raises(ValidationError, match="should match pattern"):
        AuthSettings()


@pytest.mark.unit
def test_base_url_strips_surrounding_whitespace(monkeypatch: pytest.MonkeyPatch):
    """Whitespace-padded env values from copy-paste are stripped before pattern."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "  https://staging.example.com\t")
    settings = AuthSettings()
    assert settings.base_url == "https://staging.example.com"


@pytest.mark.unit
def test_base_url_accepts_uppercase_scheme(monkeypatch: pytest.MonkeyPatch):
    """RFC 3986 section 3.1: URL scheme is case-insensitive."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "HTTPS://staging.example.com")
    settings = AuthSettings()
    assert settings.base_url == "HTTPS://staging.example.com"


@pytest.mark.unit
def test_service_account_url_strips_trailing_slash_on_base(
    monkeypatch: pytest.MonkeyPatch,
):
    """A trailing slash on ``PIPEFY_BASE_URL`` doesn't double the joiner."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://staging.example.com/")
    settings = AuthSettings()
    assert settings.service_account_url == "https://staging.example.com/oauth/token"


@pytest.mark.unit
def test_disable_stored_session_env_var_parses_true(
    monkeypatch: pytest.MonkeyPatch,
):
    """``PIPEFY_AUTH_DISABLE_STORED_SESSION=1`` flips the kill-switch on."""
    monkeypatch.setenv("PIPEFY_AUTH_DISABLE_STORED_SESSION", "1")
    settings = AuthSettings()
    assert settings.disable_stored_session is True
    assert settings.to_oidc_client() is None


@pytest.mark.unit
def test_disable_stored_session_defaults_to_false_with_oidc_client_present():
    """Default settings leave the stored-session tier enabled."""
    settings = AuthSettings()
    assert settings.disable_stored_session is False
    assert settings.to_oidc_client() is not None


@pytest.mark.unit
def test_keychain_backend_env_var_parses_file(monkeypatch: pytest.MonkeyPatch):
    """``PIPEFY_AUTH_KEYCHAIN_BACKEND=file`` picks the file backend choice."""
    monkeypatch.setenv("PIPEFY_AUTH_KEYCHAIN_BACKEND", "file")
    settings = AuthSettings()
    assert settings.keychain_backend == "file"


@pytest.mark.unit
def test_keychain_backend_defaults_to_auto():
    """Default settings preserve the OS-keyring auto-discovery."""
    assert AuthSettings().keychain_backend == "auto"


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["plaintext", "", "   "])
def test_keychain_backend_rejects_unknown_value(
    monkeypatch: pytest.MonkeyPatch, bad: str
):
    """Only ``auto`` and ``file`` are valid; anything else (including empty / whitespace-only) raises."""
    from pydantic import ValidationError

    monkeypatch.setenv("PIPEFY_AUTH_KEYCHAIN_BACKEND", bad)
    with pytest.raises(ValidationError):
        AuthSettings()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        ("AUTO", "auto"),
        (" AUTO ", "auto"),
        ("File", "file"),
        ("FILE", "file"),
        ("\tauto\n", "auto"),
    ],
)
def test_keychain_backend_normalizes_case_and_whitespace(
    monkeypatch: pytest.MonkeyPatch, env_value: str, expected: str
):
    """``_normalize_keychain_backend`` strip+lowers so copy-paste env values still match the Literal."""
    monkeypatch.setenv("PIPEFY_AUTH_KEYCHAIN_BACKEND", env_value)
    settings = AuthSettings()
    assert settings.keychain_backend == expected


@pytest.mark.unit
@pytest.mark.parametrize("padded", [" 1 ", " true ", "\tfalse\n"])
def test_keychain_backend_and_kill_switch_strip_whitespace(
    monkeypatch: pytest.MonkeyPatch, padded: str
):
    """Stray whitespace on env values is stripped before Literal / bool parsing."""
    monkeypatch.setenv("PIPEFY_AUTH_DISABLE_STORED_SESSION", padded)
    # No raise: bool parser sees the stripped value.
    AuthSettings()
