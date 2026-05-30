"""Orchestrate the Authorization Code + PKCE login against a Pipefy OIDC issuer."""

from __future__ import annotations

import secrets
import webbrowser
from dataclasses import dataclass
from typing import Callable, cast
from urllib.parse import urlencode

import httpx

from pipefy_auth import _http
from pipefy_auth.discovery import (
    DiscoveryPolicy,
    ProviderMetadata,
    fetch_provider_metadata,
)
from pipefy_auth.loopback import CallbackResult, LoopbackCapture
from pipefy_auth.pkce import challenge_from_verifier, generate_verifier
from pipefy_auth.responses import OAuthErrorResponse, TokenResponse

_DEFAULT_SCOPES = ("openid", "profile", "email", "offline_access")
_TOKEN_EXCHANGE_TIMEOUT_S = 30.0


class LoginError(RuntimeError):
    """User-facing failure during the login flow (rendered verbatim by the CLI)."""


@dataclass(frozen=True)
class LoginResult:
    """The OAuth token, plus the resolved issuer (post-discovery)."""

    issuer: str
    token: TokenResponse


def build_authorization_url(
    *,
    metadata: ProviderMetadata,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    state: str,
    scopes: tuple[str, ...] = _DEFAULT_SCOPES,
) -> str:
    """Construct the URL the user's browser should open to begin login."""
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{metadata.authorization_endpoint}?{urlencode(params)}"


def exchange_code(
    *,
    metadata: ProviderMetadata,
    client_id: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    client: httpx.Client,
) -> TokenResponse:
    """Exchange an authorization code for tokens at the issuer's token endpoint."""
    try:
        response = client.post(
            metadata.token_endpoint,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
        )
    except httpx.HTTPError as exc:
        raise LoginError(f"Token exchange request failed: {exc}") from exc

    if response.status_code != 200:
        # ``error_description`` is free-form per RFC 6749 §5.2 — its content
        # reflects the IdP's framing, and surfacing it at all is part of trusting
        # the IdP. A length cap wouldn't change that (an attacker can truncate
        # to fit any cap, and a tight cap kills legitimate error context).
        raise LoginError(
            OAuthErrorResponse.from_response(response).render(
                fallback=f"Token endpoint returned HTTP {response.status_code}",
                prefix="Token exchange failed",
            )
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise LoginError(f"Token endpoint returned non-JSON response: {exc}") from exc
    if not isinstance(payload, dict):
        raise LoginError("Token endpoint returned a non-object JSON payload.")
    try:
        return TokenResponse.from_payload(payload)
    except ValueError as exc:
        raise LoginError(str(exc)) from exc


def run_login(
    *,
    issuer_url: str,
    client_id: str,
    scopes: tuple[str, ...] = _DEFAULT_SCOPES,
    callback_timeout_s: float = 180.0,
    open_browser: Callable[[str], bool] = webbrowser.open,
    on_url: Callable[[str], None] | None = None,
    http_client: httpx.Client | None = None,
    discovery_policy: DiscoveryPolicy = DiscoveryPolicy(),
) -> LoginResult:
    """Run the full PKCE loopback login. Returns tokens; does **not** persist them.

    Args:
        issuer_url: OIDC issuer URL (e.g. ``https://signin.pipefy.com/realms/pipefy``).
        client_id: Public client id registered for the CLI.
        scopes: Scopes to request. Must include ``offline_access`` for a refresh
            token to be issued.
        callback_timeout_s: Seconds to wait for the browser callback.
        open_browser: Launch the browser at ``auth_url``. Returns ``True`` if a
            browser was launched; ``False`` otherwise (``--no-browser`` mode or
            the OS couldn't open one).
        on_url: Called with ``auth_url`` only when ``open_browser`` returned
            ``False`` — i.e., the user needs to open the URL by hand. Pass
            ``None`` to skip the fallback (callers must then handle the
            ``False`` return themselves).
        http_client: Optional pre-configured ``httpx.Client`` (testing). When
            omitted, one client is created and reused for discovery + token
            exchange so the same TLS connection can serve both requests.
        discovery_policy: Validation knobs forwarded to
            :func:`fetch_provider_metadata` (notably ``allow_insecure_urls``
            for local-development IdPs over http / private IPs).

    Raises:
        LoginError: For any user-visible failure (discovery, state mismatch,
            token exchange).
        TimeoutError: When no browser callback arrives in time.
    """
    with _http.http_client(http_client, timeout=_TOKEN_EXCHANGE_TIMEOUT_S) as http:
        try:
            metadata = fetch_provider_metadata(
                issuer_url, policy=discovery_policy, client=http
            )
        except ValueError as exc:
            raise LoginError(str(exc)) from exc

        # Bind the loopback server *before* opening the browser so no other
        # process can grab the ephemeral port in between. The `with` block
        # guarantees the socket is released even if a step before
        # `await_callback` raises.
        with LoopbackCapture() as capture:
            verifier = generate_verifier()
            state = secrets.token_urlsafe(24)
            auth_url = build_authorization_url(
                metadata=metadata,
                client_id=client_id,
                redirect_uri=capture.redirect_uri,
                code_challenge=challenge_from_verifier(verifier),
                state=state,
                scopes=scopes,
            )
            if not open_browser(auth_url) and on_url is not None:
                on_url(auth_url)

            callback = capture.await_callback(timeout=callback_timeout_s)
            _ensure_callback_ok(callback, expected_state=state)
            code = cast(str, callback.code)

            token = exchange_code(
                metadata=metadata,
                client_id=client_id,
                code=code,
                redirect_uri=capture.redirect_uri,
                code_verifier=verifier,
                client=http,
            )
    return LoginResult(issuer=metadata.issuer, token=token)


def _ensure_callback_ok(callback: CallbackResult, *, expected_state: str) -> None:
    if callback.error:
        detail = callback.error_description or ""
        suffix = f": {detail}" if detail else ""
        raise LoginError(f"Authorization server returned {callback.error}{suffix}")
    if callback.state != expected_state:
        raise LoginError(
            "State mismatch on OAuth callback (possible CSRF). Aborting login."
        )
    if not callback.code:
        raise LoginError("OAuth callback did not include an authorization code.")


__all__ = [
    "LoginError",
    "LoginResult",
    "build_authorization_url",
    "exchange_code",
    "run_login",
]
