"""Auth settings: the pure value object plus the ``PIPEFY_AUTH_*`` env contract.

``AuthSettings`` is a pure value object now: it validates kwargs but reads no env.
The ``PIPEFY_AUTH_*`` / ``PIPEFY_TOKEN`` / ``PIPEFY_SERVICE_ACCOUNT_*`` env-name
contract (and the no-leak guarantee) lives in the edge reader
:func:`pipefy_infra.config.read_auth_env`, exercised here against the auth field
names it feeds. ``base_url`` is no longer an auth field: the OAuth token URL is
injected as ``service_account_token_url`` (derived from the SDK base_url and
covered by the CLI / MCP resolver tests).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pipefy_infra.config import read_auth_env

from pipefy_auth.settings import AuthSettings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Clear every ``PIPEFY_*`` env and pin ``PIPEFY_CONFIG_FILE`` at a tmp path.

    The reader tests assert prod defaults and the absence of leaked credentials,
    so any ambient ``PIPEFY_*`` var or a stray ``~/.config/pipefy/config.toml``
    on a dev machine would otherwise bleed in.
    """
    for key in list(os.environ):
        if key.startswith("PIPEFY_") or key in {"XDG_CONFIG_HOME", "APPDATA"}:
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(tmp_path / "config.toml"))


# --------------------------------------------------------------------------- #
# Pure value object: validation, normalization, projection (kwargs, no env).
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_issuer_url_defaults_to_pipefy_prod_idp():
    """``AuthSettings()`` with no kwargs defaults to the Pipefy prod IdP."""
    settings = AuthSettings()
    assert settings.issuer_url == "https://signin.pipefy.com/realms/pipefy"
    oidc = settings.to_oidc_client()
    assert oidc.issuer_url == "https://signin.pipefy.com/realms/pipefy"


@pytest.mark.unit
def test_service_account_token_url_is_injected_not_derived():
    """The token URL is injected (from the SDK base_url), not read off auth."""
    settings = AuthSettings(
        service_account_token_url="https://staging.example.com/oauth/token",
        service_account_client_id="cid",
        service_account_client_secret="sec",
    )
    sa = settings.to_service_account()
    assert sa is not None
    assert sa.token_url == "https://staging.example.com/oauth/token"


@pytest.mark.unit
def test_to_service_account_is_none_without_token_url():
    """An incomplete triple (no injected token URL) projects to None."""
    settings = AuthSettings(
        service_account_client_id="cid", service_account_client_secret="sec"
    )
    assert settings.to_service_account() is None


@pytest.mark.unit
def test_empty_issuer_url_rejected():
    """An empty ``issuer_url`` is rejected by pattern validation at construction."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="should match pattern"):
        AuthSettings(issuer_url="")


@pytest.mark.unit
def test_insecure_issuer_rejected_without_injected_flag():
    """http:// issuers are rejected unless the injected insecure flag is set."""
    with pytest.raises(ValueError):
        AuthSettings(issuer_url="http://idp.internal/realms/x")


@pytest.mark.unit
def test_insecure_issuer_allowed_with_injected_flag():
    """The injected allow_insecure_urls relaxes the issuer scheme / host gate."""
    settings = AuthSettings(
        issuer_url="http://127.0.0.1:8080/realms/x", allow_insecure_urls=True
    )
    assert settings.issuer_url == "http://127.0.0.1:8080/realms/x"


@pytest.mark.unit
def test_disable_stored_session_projects_to_no_oidc_client():
    """The kill-switch turns off the stored-session tier."""
    assert AuthSettings(disable_stored_session=True).to_oidc_client() is None


@pytest.mark.unit
def test_disable_stored_session_defaults_to_false_with_oidc_client_present():
    """Default settings leave the stored-session tier enabled."""
    settings = AuthSettings()
    assert settings.disable_stored_session is False
    assert settings.to_oidc_client() is not None


@pytest.mark.unit
def test_keychain_backend_defaults_to_auto():
    """Default settings preserve the OS-keyring auto-discovery."""
    assert AuthSettings().keychain_backend == "auto"


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["plaintext", "", "   "])
def test_keychain_backend_rejects_unknown_value(bad: str):
    """Only ``auto`` and ``file`` are valid; anything else (incl. empty/blank) raises."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AuthSettings(keychain_backend=bad)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("AUTO", "auto"),
        (" AUTO ", "auto"),
        ("File", "file"),
        ("FILE", "file"),
        ("\tauto\n", "auto"),
    ],
)
def test_keychain_backend_normalizes_case_and_whitespace(value: str, expected: str):
    """``_normalize_keychain_backend`` strip+lowers so copy-paste values still match."""
    assert AuthSettings(keychain_backend=value).keychain_backend == expected


# --------------------------------------------------------------------------- #
# Env-name contract: read_auth_env owns PIPEFY_AUTH_* / PIPEFY_TOKEN / ...
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_reader_maps_pipefy_auth_issuer_url(monkeypatch: pytest.MonkeyPatch):
    """``PIPEFY_AUTH_ISSUER_URL`` feeds the ``issuer_url`` field."""
    monkeypatch.setenv("PIPEFY_AUTH_ISSUER_URL", "https://other.example.com/realms/x")
    raw = read_auth_env()
    assert raw["issuer_url"] == "https://other.example.com/realms/x"
    assert AuthSettings(**raw).issuer_url == "https://other.example.com/realms/x"


@pytest.mark.unit
def test_reader_maps_canonical_credential_vars(monkeypatch: pytest.MonkeyPatch):
    """The credentials keep their canonical (unprefixed) env names through the reader."""
    monkeypatch.setenv("PIPEFY_TOKEN", "tok")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_ID", "cid")
    monkeypatch.setenv("PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET", "sec")
    raw = read_auth_env()
    assert raw["static_token"] == "tok"
    assert raw["service_account_client_id"] == "cid"
    assert raw["service_account_client_secret"] == "sec"


@pytest.mark.unit
def test_reader_parses_disable_stored_session(monkeypatch: pytest.MonkeyPatch):
    """``PIPEFY_AUTH_DISABLE_STORED_SESSION=1`` parses to a bool at the reader."""
    monkeypatch.setenv("PIPEFY_AUTH_DISABLE_STORED_SESSION", "1")
    assert read_auth_env()["disable_stored_session"] is True


@pytest.mark.unit
def test_reader_reads_keychain_backend(monkeypatch: pytest.MonkeyPatch):
    """``PIPEFY_AUTH_KEYCHAIN_BACKEND`` is read raw (the model normalizes it)."""
    monkeypatch.setenv("PIPEFY_AUTH_KEYCHAIN_BACKEND", "file")
    assert read_auth_env()["keychain_backend"] == "file"


@pytest.mark.unit
def test_bare_name_env_vars_do_not_leak_through_reader(monkeypatch: pytest.MonkeyPatch):
    """Unprefixed / wrong-prefixed env vars must not be honored by the reader.

    pydantic-settings env loading is case-insensitive, so an unprefixed alias
    would let any bare-name host var bleed into Pipefy auth, an auth-redirect /
    credential-leak primitive. The canonical aliases are the sole env names.
    """
    monkeypatch.setenv("BASE_URL", "https://evil.example.com")
    monkeypatch.setenv("STATIC_TOKEN", "leaked")
    monkeypatch.setenv("TOKEN", "leaked")
    monkeypatch.setenv("ISSUER_URL", "https://evil.example.com/realms/x")
    # Prefixed forms of the alias-pinned credential are inert too (the alias is
    # the sole env name, per _AliasOwnsEnvNameMixin).
    monkeypatch.setenv("PIPEFY_AUTH_STATIC_TOKEN", "leaked")
    assert read_auth_env() == {}
