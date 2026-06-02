"""Typed OAuth response wrappers (RFC 6749 §5.1 success, §5.2 error;
RFC 8628 §3.5 error).

``TokenResponse`` parses the token-endpoint success body. ``OAuthErrorResponse``
parses the error envelope; the call site supplies the rendering prefix and
fallback so endpoint context stays out of the wire-shape model.
"""

from __future__ import annotations

from typing import Annotated

import httpx
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    ValidationError,
)


def _strip_or_none(value: object) -> str | None:
    """Strip strings to ``None`` on empty; drop non-strings to ``None``.

    Non-string drop is load-bearing for :meth:`OAuthErrorResponse.from_response`:
    callers invoke ``.render(...)`` inline without a try, so a non-string
    ``error`` field must fall through to the fallback rather than raise.
    """
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


_OptionalStr = Annotated[str | None, BeforeValidator(_strip_or_none)]


class TokenResponse(BaseModel):
    """Parsed OAuth 2.0 token-endpoint success response (RFC 6749 §5.1).

    Strict typing: ``StrictStr`` rejects bool/None coercion; ``StrictInt``
    rejects bool (``isinstance(True, int)`` is ``True`` in Python, so plain
    ``int`` would accept a boolean lifetime). Unknown fields are ignored
    because IdPs (Keycloak) routinely add proprietary keys like
    ``not-before-policy`` / ``session_state``.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    access_token: Annotated[StrictStr, Field(min_length=1)]
    refresh_token: Annotated[StrictStr, Field(min_length=1)]
    token_type: StrictStr = "Bearer"
    expires_in: StrictInt | None = None
    refresh_expires_in: StrictInt | None = None
    scope: _OptionalStr = None
    id_token: _OptionalStr = None

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "TokenResponse":
        return cls.model_validate(payload)


class OAuthErrorResponse(BaseModel):
    """Parsed OAuth error envelope (RFC 6749 §5.2 / RFC 8628 §3.5).

    ``error`` is ``None`` when the body wasn't OAuth-shaped (non-JSON,
    non-dict, missing ``error``); callers render that case via :meth:`render`'s
    ``fallback`` argument.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    status_code: StrictInt
    error: _OptionalStr = None
    error_description: _OptionalStr = None

    @classmethod
    def from_response(cls, response: httpx.Response) -> "OAuthErrorResponse":
        try:
            payload = response.json()
        except ValueError:
            payload = None
        body = payload if isinstance(payload, dict) else {}
        return cls.model_validate(
            {
                "status_code": response.status_code,
                "error": body.get("error"),
                "error_description": body.get("error_description"),
            }
        )

    def render(self, *, fallback: str, prefix: str) -> str:
        """Return a user-safe message; never echoes the raw body.

        Returns ``fallback`` when the response wasn't OAuth-shaped. ``prefix``
        names the failed action (e.g. ``"Token exchange failed"``).
        """
        if not self.error:
            return fallback
        if self.error_description:
            return f"{prefix}: {self.error}: {self.error_description}"
        return f"{prefix}: {self.error}"


def _format_validation_error(exc: ValidationError) -> str:
    """Render a pydantic ``ValidationError`` as a compact ``"loc: msg"`` list.

    Mirrors :func:`pipefy_mcp.tools.portal_tool_helpers.portal_element_validation_error`
    so auth-facing messages match the MCP-tool shape. Avoids pydantic's verbose
    default ``str(exc)`` (which includes doc URLs) on user-facing surfaces.
    """
    clauses: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", ()))
        msg = str(err.get("msg", ""))
        if loc and msg:
            clauses.append(f"{loc}: {msg}")
        elif msg:
            clauses.append(msg)
    return "; ".join(clauses) or "Response failed validation."


__all__ = ["OAuthErrorResponse", "TokenResponse"]
