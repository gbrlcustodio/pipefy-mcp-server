"""Typed OAuth response wrappers (RFC 6749 §5.1 success, §5.2 error;
RFC 8628 §3.5 error).

``TokenResponse`` parses the token-endpoint success body. ``OAuthErrorResponse``
parses the error envelope; the call site supplies the rendering prefix and
fallback so endpoint context stays out of the wire-shape model.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from pipefy_infra.coerce import optional_int, optional_str


@dataclass(frozen=True)
class TokenResponse:
    """Parsed OAuth 2.0 token-endpoint success response (RFC 6749 §5.1).

    ``expires_in`` and ``refresh_expires_in`` silently coerce to ``None`` on
    non-numeric values so an unparseable lifetime does not block the response
    from being constructed.
    """

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_expires_in: int | None = None
    scope: str | None = None
    id_token: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "TokenResponse":
        try:
            access_token = str(payload["access_token"])
            refresh_token = str(payload["refresh_token"])
        except KeyError as exc:
            raise ValueError(
                f"Token response is missing required field: {exc.args[0]!r}"
            ) from exc
        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=str(payload.get("token_type") or "Bearer"),
            expires_in=optional_int(payload.get("expires_in")),
            refresh_expires_in=optional_int(payload.get("refresh_expires_in")),
            scope=optional_str(payload.get("scope")),
            id_token=optional_str(payload.get("id_token")),
        )


@dataclass(frozen=True)
class OAuthErrorResponse:
    """Parsed OAuth error envelope (RFC 6749 §5.2 / RFC 8628 §3.5).

    ``error`` is ``None`` when the body wasn't OAuth-shaped (non-JSON,
    non-dict, missing ``error``); callers render that case via :meth:`render`'s
    ``fallback`` argument.
    """

    status_code: int
    error: str | None
    error_description: str | None

    @classmethod
    def from_response(cls, response: httpx.Response) -> "OAuthErrorResponse":
        error: str | None = None
        description: str | None = None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            error = optional_str(payload.get("error"))
            description = optional_str(payload.get("error_description"))
        return cls(
            status_code=response.status_code,
            error=error,
            error_description=description,
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


__all__ = ["OAuthErrorResponse", "TokenResponse"]
