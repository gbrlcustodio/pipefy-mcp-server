"""Back-compat coverage for the ``PIPEFY_OAUTH_*`` → ``PIPEFY_SERVICE_ACCOUNT_*`` rename
and the ``PIPEFY_BASE_URL`` rewrite (issue #238).

The legacy ``PIPEFY_OAUTH_CLIENT`` / ``PIPEFY_OAUTH_SECRET`` env vars and
``oauth_client`` / ``oauth_secret`` TOML keys are still honored via an
``AliasChoices`` shim plus a one-shot stderr deprecation warning. These
tests pin both behaviors so the eventual PR that drops the aliases (and
the warning) has a clear regression surface.

The ``PIPEFY_OAUTH_URL`` legacy alias was dropped — the OAuth token
endpoint now derives from ``PIPEFY_BASE_URL``.
"""

from __future__ import annotations

import pytest

from pipefy_auth.settings import (
    _LEGACY_ENV_KEYS_TO_NEW,
    AuthSettings,
    _reset_legacy_oauth_warning_state,
    _warn_once_for_legacy_oauth_env_keys,
)


@pytest.fixture(autouse=True)
def _reset_warning_dedup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test sees a fresh warning dedup set and a clean process env."""
    for key in _LEGACY_ENV_KEYS_TO_NEW:
        monkeypatch.delenv(key, raising=False)
    for key in _LEGACY_ENV_KEYS_TO_NEW.values():
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("PIPEFY_OAUTH_URL", raising=False)
    monkeypatch.delenv("PIPEFY_SERVICE_ACCOUNT_URL", raising=False)
    monkeypatch.delenv("PIPEFY_BASE_URL", raising=False)
    monkeypatch.delenv("PIPEFY_AUTH_URL", raising=False)
    _reset_legacy_oauth_warning_state()
    yield
    _reset_legacy_oauth_warning_state()


@pytest.mark.unit
def test_bare_name_env_vars_do_not_leak_into_auth_settings(
    monkeypatch: pytest.MonkeyPatch,
):
    """Unprefixed env vars (``BASE_URL``, ``STATIC_TOKEN``, ``OAUTH_CLIENT``, ...) must not be honored.

    pydantic-settings env loading is case-insensitive by default, so an
    unprefixed alias on ``AliasChoices`` would let any bare-name env var
    on the host bleed into Pipefy auth settings — an auth-redirect /
    credential-leak primitive.
    """
    monkeypatch.setenv("BASE_URL", "https://evil.example.com")
    monkeypatch.setenv("STATIC_TOKEN", "leaked")
    monkeypatch.setenv("OAUTH_CLIENT", "leaked-client")
    monkeypatch.setenv("OAUTH_SECRET", "leaked-secret")
    monkeypatch.setenv("ALLOW_INSECURE_URLS", "true")
    settings = AuthSettings()
    assert settings.base_url == "https://app.pipefy.com"  # default, not leaked
    assert settings.static_token is None
    assert settings.service_account_client_id is None
    assert settings.service_account_client_secret is None
    assert settings.allow_insecure_urls is False


@pytest.mark.unit
def test_new_kwargs_populate_new_fields():
    s = AuthSettings(
        service_account_client_id="new-client",
        service_account_client_secret="new-secret",
    )
    assert s.service_account_client_id == "new-client"
    assert s.service_account_client_secret == "new-secret"


@pytest.mark.unit
def test_legacy_env_var_emits_deprecation_warning(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("PIPEFY_OAUTH_CLIENT", "legacy-client")
    _warn_once_for_legacy_oauth_env_keys()
    err = capsys.readouterr().err
    assert "PIPEFY_OAUTH_CLIENT is deprecated" in err
    assert "rename to PIPEFY_SERVICE_ACCOUNT_CLIENT_ID" in err


@pytest.mark.unit
def test_deprecation_warning_dedups_within_process(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("PIPEFY_OAUTH_CLIENT", "legacy-client")
    _warn_once_for_legacy_oauth_env_keys()
    _warn_once_for_legacy_oauth_env_keys()
    _warn_once_for_legacy_oauth_env_keys()
    err = capsys.readouterr().err
    assert err.count("PIPEFY_OAUTH_CLIENT is deprecated") == 1


@pytest.mark.unit
def test_no_deprecation_warning_when_only_new_env_keys_set(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "new-client")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "new-secret")
    _warn_once_for_legacy_oauth_env_keys()
    err = capsys.readouterr().err
    assert "deprecated" not in err


@pytest.mark.unit
def test_base_url_defaults_to_prod():
    """``AuthSettings()`` with no env defaults to the Pipefy prod API host."""
    settings = AuthSettings()
    assert settings.base_url == "https://app.pipefy.com"
    assert settings.service_account_url == "https://app.pipefy.com/oauth/token"


@pytest.mark.unit
def test_auth_url_defaults_to_pipefy_prod_idp():
    """``AuthSettings()`` with no env defaults to the Pipefy prod IdP."""
    settings = AuthSettings()
    assert settings.auth_url == "https://signin.pipefy.com/realms/pipefy"
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
def test_pipefy_auth_url_env_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
):
    """``PIPEFY_AUTH_URL`` overrides the default issuer URL."""
    monkeypatch.setenv("PIPEFY_AUTH_URL", "https://other.example.com/realms/x")
    settings = AuthSettings()
    assert settings.auth_url == "https://other.example.com/realms/x"


@pytest.mark.unit
@pytest.mark.parametrize(
    "env_key",
    ["PIPEFY_BASE_URL", "PIPEFY_AUTH_URL"],
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
    """RFC 3986 §3.1: URL scheme is case-insensitive."""
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
    """``PIPEFY_DISABLE_STORED_SESSION=1`` flips the kill-switch on."""
    monkeypatch.setenv("PIPEFY_DISABLE_STORED_SESSION", "1")
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
    """``PIPEFY_KEYCHAIN_BACKEND=file`` picks the file backend choice."""
    monkeypatch.setenv("PIPEFY_KEYCHAIN_BACKEND", "file")
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
    """Only ``auto``, ``file`` and ``encrypted`` are valid; anything else (including empty / whitespace-only) raises."""
    from pydantic import ValidationError

    monkeypatch.setenv("PIPEFY_KEYCHAIN_BACKEND", bad)
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
    monkeypatch.setenv("PIPEFY_KEYCHAIN_BACKEND", env_value)
    settings = AuthSettings()
    assert settings.keychain_backend == expected


@pytest.mark.unit
@pytest.mark.parametrize("padded", [" 1 ", " true ", "\tfalse\n"])
def test_keychain_backend_and_kill_switch_strip_whitespace(
    monkeypatch: pytest.MonkeyPatch, padded: str
):
    """Stray whitespace on env values is stripped before Literal / bool parsing."""
    monkeypatch.setenv("PIPEFY_DISABLE_STORED_SESSION", padded)
    # No raise: bool parser sees the stripped value.
    AuthSettings()


@pytest.mark.unit
@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_encrypted_backend_is_accepted_on_macos_and_windows(
    monkeypatch: pytest.MonkeyPatch, platform: str
):
    monkeypatch.setattr("pipefy_auth.settings.sys.platform", platform)
    monkeypatch.setenv("PIPEFY_KEYCHAIN_BACKEND", " Encrypted ")
    assert AuthSettings().keychain_backend == "encrypted"


@pytest.mark.unit
def test_keychain_backend_normalizes_class_name_aliases(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PIPEFY_KEYCHAIN_BACKEND", "EncryptedFileKeyring")
    monkeypatch.setattr("pipefy_auth.settings.sys.platform", "darwin")
    assert AuthSettings().keychain_backend == "encrypted"
    monkeypatch.setenv("PIPEFY_KEYCHAIN_BACKEND", "PlaintextKeyring")
    assert AuthSettings().keychain_backend == "file"


@pytest.mark.unit
@pytest.mark.parametrize("platform", ["linux", "freebsd"])
def test_encrypted_backend_is_rejected_off_macos_and_windows(
    monkeypatch: pytest.MonkeyPatch, platform: str
):
    from pydantic import ValidationError

    monkeypatch.setattr("pipefy_auth.settings.sys.platform", platform)
    monkeypatch.setenv("PIPEFY_KEYCHAIN_BACKEND", "encrypted")
    with pytest.raises(ValidationError, match="only supported on macOS and Windows"):
        AuthSettings()
