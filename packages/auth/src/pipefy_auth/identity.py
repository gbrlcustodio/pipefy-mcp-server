"""OIDC client identity shared by every consumer of the stored user session."""

from __future__ import annotations

from typing import Self

from pipefy_infra import security
from pipefy_infra.coerce import OPAQUE_CREDENTIAL_PATTERN
from pydantic import BaseModel, ConfigDict, Field, model_validator

# Refresh tokens are bound to the client_id that obtained them, so this value
# is fixed across consumers (CLI, MCP, …) and not user-configurable.
DEFAULT_AUTH_CLIENT_ID = "pipefy-cli"


class OidcClient(BaseModel):
    """OIDC client identity: issuer URL + the public client id registered there.

    A frozen, refined value object: construction witnesses that ``issuer_url`` is
    well-shaped (scheme + host, no query/fragment that would corrupt the
    ``.well-known/openid-configuration`` concatenation). The HTTPS-vs-insecure
    posture is a deployment-edge decision applied by the loader, not re-checked
    here. Presence of an :class:`OidcClient` is what gates the stored-session tier
    of the credential precedence chain.
    """

    model_config = ConfigDict(frozen=True)

    issuer_url: str = Field(pattern=security.URL_SHAPE_PATTERN)
    client_id: str = Field(pattern=OPAQUE_CREDENTIAL_PATTERN)

    @model_validator(mode="after")
    def _validate_url_shape(self) -> Self:
        security.assert_url_has_no_query_or_fragment(
            self.issuer_url, field_label="issuer_url"
        )
        return self


__all__ = [
    "DEFAULT_AUTH_CLIENT_ID",
    "OidcClient",
]
