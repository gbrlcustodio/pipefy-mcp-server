"""Value-object tests for ``AuthConfig`` / ``ServiceAccountCredentials``.

``AuthConfig`` is now a pure ``pydantic.BaseModel``: it reads no env (the
application edge owns that and injects ``deployment`` + ``service_account``).
These tests construct it directly with kwargs and assert defaults, the tier
projections (``to_oidc_client`` / ``to_service_account``), and the inline SSRF
gate. Env-name / precedence coverage lives at the application edge
(pipefy_cli / pipefy_mcp).
"""

from __future__ import annotations

import pytest
from pipefy_infra.deployment import DeploymentConfig
from pydantic import ValidationError

from pipefy_auth.settings import (
    DEFAULT_ISSUER_URL,
    AuthConfig,
    ServiceAccountCredentials,
)

PROD_TOKEN_URL = "https://app.pipefy.com/oauth/token"


def _auth(**kwargs) -> AuthConfig:
    """Build an AuthConfig with a default prod deployment unless one is given."""
    kwargs.setdefault("deployment", DeploymentConfig())
    return AuthConfig(**kwargs)


@pytest.mark.unit
def test_requires_injected_deployment():
    """``deployment`` has no default: the application edge must inject it."""
    with pytest.raises(ValidationError, match="deployment"):
        AuthConfig()


@pytest.mark.unit
def test_issuer_url_defaults_to_pipefy_prod_idp():
    settings = _auth()
    assert settings.issuer_url == DEFAULT_ISSUER_URL
    oidc = settings.to_oidc_client()
    assert oidc is not None
    assert oidc.issuer_url == DEFAULT_ISSUER_URL
    assert oidc.client_id == "pipefy-cli"


@pytest.mark.unit
def test_public_client_id_override():
    settings = _auth(public_client_id="custom-public-client")
    assert settings.public_client_id == "custom-public-client"
    assert settings.to_oidc_client().client_id == "custom-public-client"


@pytest.mark.unit
def test_issuer_url_override_and_shape_gate():
    settings = _auth(issuer_url="https://other.example.com/realms/x")
    assert settings.issuer_url == "https://other.example.com/realms/x"


@pytest.mark.unit
def test_issuer_url_rejects_surrounding_whitespace():
    # The value object validates but does not normalize: the edge trims env
    # whitespace, so a padded value reaching the model directly is rejected by
    # the URL shape constraint.
    with pytest.raises(ValidationError):
        _auth(issuer_url="  https://other.example.com/realms/x\t")


@pytest.mark.unit
def test_issuer_url_rejects_http_by_default():
    with pytest.raises(ValidationError, match="issuer_url.*HTTPS"):
        _auth(issuer_url="http://insecure.example.com")


@pytest.mark.unit
def test_issuer_url_http_allowed_when_deployment_insecure():
    settings = AuthConfig(
        deployment=DeploymentConfig(
            base_url="http://localhost:3000", allow_insecure_urls=True
        ),
        issuer_url="http://localhost:8080/realms/x",
    )
    assert settings.issuer_url == "http://localhost:8080/realms/x"
    assert settings.allow_insecure_urls is True


# --- service-account tier --------------------------------------------------


@pytest.mark.unit
def test_service_account_none_yields_no_service_account():
    assert _auth().service_account is None
    assert _auth().to_service_account() is None


@pytest.mark.unit
def test_service_account_projects_with_deployment_token_url():
    settings = _auth(
        service_account=ServiceAccountCredentials(
            client_id="sa-client", client_secret="sa-secret"
        )
    )
    sa = settings.to_service_account()
    assert sa is not None
    assert sa.token_url == PROD_TOKEN_URL
    assert sa.client_id == "sa-client"
    assert sa.client_secret == "sa-secret"


@pytest.mark.unit
def test_service_account_token_url_follows_custom_deployment():
    settings = AuthConfig(
        deployment=DeploymentConfig(base_url="https://staging.example.com"),
        service_account=ServiceAccountCredentials(
            client_id="sa-client", client_secret="sa-secret"
        ),
    )
    assert (
        settings.to_service_account().token_url
        == "https://staging.example.com/oauth/token"
    )


@pytest.mark.unit
def test_service_account_credentials_require_both_fields():
    with pytest.raises(ValidationError):
        ServiceAccountCredentials(client_id="only-id")
    with pytest.raises(ValidationError):
        ServiceAccountCredentials(client_secret="only-secret")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("client_id", "client_secret"),
    [("  id  ", "secret"), ("id", "\tsecret\n")],
)
def test_service_account_credentials_reject_surrounding_whitespace(
    client_id: str, client_secret: str
):
    # The credential pair validates but does not normalize; the edge trims env
    # whitespace before building it, so a padded value here is rejected.
    with pytest.raises(ValidationError):
        ServiceAccountCredentials(client_id=client_id, client_secret=client_secret)


@pytest.mark.unit
@pytest.mark.parametrize("blank", ["", "   ", " \t "])
def test_service_account_credentials_reject_blank(blank: str):
    with pytest.raises(ValidationError):
        ServiceAccountCredentials(client_id=blank, client_secret="ok")


# --- stored-session kill switch + keychain backend -------------------------


@pytest.mark.unit
def test_disable_stored_session_returns_no_oidc_client():
    settings = _auth(disable_stored_session=True)
    assert settings.disable_stored_session is True
    assert settings.to_oidc_client() is None


@pytest.mark.unit
def test_disable_stored_session_defaults_false_with_oidc_client_present():
    settings = _auth()
    assert settings.disable_stored_session is False
    assert settings.to_oidc_client() is not None


@pytest.mark.unit
def test_keychain_backend_defaults_to_auto():
    assert _auth().keychain_backend == "auto"


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
    """``_normalize_keychain_backend`` strip+lowers so copy-paste values still match the Literal."""
    assert _auth(keychain_backend=value).keychain_backend == expected


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["plaintext", "", "   "])
def test_keychain_backend_rejects_unknown_value(bad: str):
    with pytest.raises(ValidationError):
        _auth(keychain_backend=bad)


@pytest.mark.unit
def test_static_token_rejects_padded_and_blank():
    # Normalization is the edge's job; the value object rejects both a padded
    # token and a blank one via the opaque-credential shape constraint.
    with pytest.raises(ValidationError):
        _auth(static_token="  tok  ")
    with pytest.raises(ValidationError):
        _auth(static_token="   ")
