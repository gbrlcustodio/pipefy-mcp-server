"""Orchestrate the OAuth 2.0 Device Authorization Grant login (RFC 8628)."""

from __future__ import annotations

import time
from typing import Callable

import httpx
from pydantic import ValidationError

from pipefy_auth import _http
from pipefy_auth.discovery import (
    DiscoveryPolicy,
    ProviderMetadata,
    fetch_provider_metadata,
)
from pipefy_auth.flow import LoginError, LoginResult
from pipefy_auth.pkce import challenge_from_verifier, generate_verifier
from pipefy_auth.responses import (
    DeviceAuthorization,
    OAuthErrorResponse,
    TokenResponse,
    _format_validation_error,
)

_DEFAULT_SCOPES = ("openid", "profile", "email", "offline_access")
_DEVICE_AUTH_TIMEOUT_S = 30.0
_SLOW_DOWN_INCREMENT_S = 5
_DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"

_EXPIRED_TOKEN_MESSAGE = (
    "Sign-in didn't complete in time. Re-run `pipefy auth login --device` to try again."
)
_ACCESS_DENIED_MESSAGE = "Sign-in cancelled by the user."


def request_device_authorization(
    *,
    metadata: ProviderMetadata,
    client_id: str,
    code_challenge: str,
    scopes: tuple[str, ...] = _DEFAULT_SCOPES,
    client: httpx.Client,
) -> DeviceAuthorization:
    """POST to the issuer's device authorization endpoint and parse the response.

    PKCE (``code_challenge`` + ``code_challenge_method=S256``) is sent on every
    request: RFC 8628 doesn't require it, but Keycloak applies a client's
    "PKCE Code Challenge Method" setting uniformly across grant types, so a
    realm that mandates PKCE on the authorization-code path also rejects
    PKCE-less device-auth requests with ``invalid_request: Missing parameter:
    code_challenge_method``. IdPs that don't enforce PKCE accept the extra
    parameters and validate the verifier without complaint.
    """
    if metadata.device_authorization_endpoint is None:
        raise LoginError(
            "OIDC discovery did not advertise a device_authorization_endpoint. "
            "This issuer may not support device login."
        )

    try:
        response = client.post(
            metadata.device_authorization_endpoint,
            data={
                "client_id": client_id,
                "scope": " ".join(scopes),
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            },
        )
    except httpx.HTTPError as exc:
        raise LoginError(f"Device authorization request failed: {exc}") from exc

    if response.status_code != 200:
        raise LoginError(
            OAuthErrorResponse.from_response(response).render(
                fallback=f"Device authorization endpoint returned HTTP {response.status_code}",
                prefix="Device authorization failed",
            )
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise LoginError(
            f"Device authorization endpoint returned non-JSON response: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise LoginError(
            "Device authorization endpoint returned a non-object JSON payload."
        )

    try:
        return DeviceAuthorization.from_payload(payload)
    except ValidationError as exc:
        raise LoginError(_format_validation_error(exc)) from exc


def poll_device_token(
    *,
    metadata: ProviderMetadata,
    client_id: str,
    code_verifier: str,
    device_auth: DeviceAuthorization,
    client: httpx.Client,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> TokenResponse:
    """Poll the token endpoint until authorization completes or the device code expires."""
    deadline = monotonic() + device_auth.expires_in
    interval = device_auth.interval

    while True:
        if monotonic() >= deadline:
            raise LoginError(_EXPIRED_TOKEN_MESSAGE)

        try:
            response = client.post(
                metadata.token_endpoint,
                data={
                    "grant_type": _DEVICE_GRANT_TYPE,
                    "device_code": device_auth.device_code,
                    "client_id": client_id,
                    "code_verifier": code_verifier,
                },
            )
        except httpx.HTTPError as exc:
            raise LoginError(f"Device token poll request failed: {exc}") from exc

        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError as exc:
                raise LoginError(
                    f"Token endpoint returned non-JSON response: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise LoginError("Token endpoint returned a non-object JSON payload.")
            try:
                return TokenResponse.from_payload(payload)
            except ValidationError as exc:
                raise LoginError(_format_validation_error(exc)) from exc

        err = OAuthErrorResponse.from_response(response)
        if err.error == "expired_token":
            raise LoginError(_EXPIRED_TOKEN_MESSAGE)
        if err.error == "access_denied":
            raise LoginError(_ACCESS_DENIED_MESSAGE)
        if err.error == "slow_down":
            interval += _SLOW_DOWN_INCREMENT_S
        elif err.error != "authorization_pending":
            raise LoginError(
                err.render(
                    fallback=f"Token endpoint returned HTTP {response.status_code}",
                    prefix="Device token poll failed",
                )
            )

        wait_s = min(interval, deadline - monotonic())
        if wait_s > 0:
            sleep(wait_s)


def run_device_login(
    *,
    issuer_url: str,
    client_id: str,
    scopes: tuple[str, ...] = _DEFAULT_SCOPES,
    on_device_info: Callable[[DeviceAuthorization], None] | None = None,
    http_client: httpx.Client | None = None,
    discovery_policy: DiscoveryPolicy = DiscoveryPolicy(),
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> LoginResult:
    """Run the full device authorization grant. Returns tokens; does **not** persist them."""
    with _http.http_client(http_client, timeout=_DEVICE_AUTH_TIMEOUT_S) as http:
        try:
            metadata = fetch_provider_metadata(
                issuer_url, policy=discovery_policy, client=http
            )
        except ValueError as exc:
            raise LoginError(str(exc)) from exc

        verifier = generate_verifier()
        device_auth = request_device_authorization(
            metadata=metadata,
            client_id=client_id,
            code_challenge=challenge_from_verifier(verifier),
            scopes=scopes,
            client=http,
        )
        if on_device_info is not None:
            on_device_info(device_auth)

        token = poll_device_token(
            metadata=metadata,
            client_id=client_id,
            code_verifier=verifier,
            device_auth=device_auth,
            client=http,
            sleep=sleep,
            monotonic=monotonic,
        )
    return LoginResult(issuer=metadata.issuer, token=token)


__all__ = [
    "DeviceAuthorization",
    "poll_device_token",
    "request_device_authorization",
    "run_device_login",
]
