"""Interactive user authentication via OAuth 2.0 Authorization Code + PKCE."""

from __future__ import annotations

import asyncio
import os
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import typer
from gql.transport.exceptions import (
    TransportError,
    TransportQueryError,
    TransportServerError,
)
from pipefy_auth import (
    DiscoveryPolicy,
    LoginError,
    OidcClient,
    RefreshError,
    RevocationError,
    RevocationUnsupportedError,
    SessionDeleteError,
    StoredSessionAuth,
    delete_session,
    ensure_fresh_session,
    keychain_backend_name,
    load_session,
    revoke_session,
    run_login,
    store_session,
)
from pipefy_auth.settings import _LEGACY_ENV_KEYS_TO_NEW
from pipefy_sdk import MePayload, PipefySettings

from pipefy_cli._docs import DOCS_CLI_AUTH_REF
from pipefy_cli.auth import (
    AuthContext,
    DisplaySource,
    detect_cli_auth_methods,
    get_authenticated_client,
    to_display_source,
)
from pipefy_cli.commands._common import settings_and_auth_from_ctx
from pipefy_cli.output import render_json

AuthSessionState = Literal["active", "refresh-expired", "needs-login", "n/a"]


@dataclass
class AuthStatusReport:
    """Typed model for `auth status` rendering.

    Distinct from the locked JSON wire schema (see :func:`_to_json_payload`):
    renderers consume this typed value, not the wire dict, so the external
    contract and the internal model can evolve independently.
    """

    auth_source: DisplaySource
    detected_sources: list[DisplaySource]
    issuer: str | None = None
    state: AuthSessionState = "n/a"
    access_expires_at: str | None = None
    refresh_expires_at: str | None = None
    identity: MePayload | None = None
    token_rejected: bool = False
    keychain_backend: str | None = None
    masking_env_vars: list[str] = field(default_factory=list)

    @property
    def signed_in(self) -> bool:
        return self.auth_source != "none"


auth_app = typer.Typer(
    help="Authenticate the CLI as your Pipefy user (browser-based login).",
    no_args_is_help=True,
)

_SERVICE_ACCOUNT_ENV_KEYS = tuple(_LEGACY_ENV_KEYS_TO_NEW.values())
_LEGACY_SERVICE_ACCOUNT_ENV_KEYS = tuple(_LEGACY_ENV_KEYS_TO_NEW.keys())


def _session_masking_env_vars() -> list[str]:
    """Env vars in ``os.environ`` that outrank a stored session.

    A service-account triple counts only when *complete* (otherwise the
    client-credentials path wouldn't activate and the warning would mislead).
    Both the canonical and legacy forms are accepted during the deprecation
    window, and the label echoes whichever the user actually set so they know
    which keys to unset.
    """
    env_vars: list[str] = []
    if os.environ.get("PIPEFY_TOKEN"):
        env_vars.append("PIPEFY_TOKEN")
    if all(os.environ.get(k) for k in _SERVICE_ACCOUNT_ENV_KEYS):
        env_vars.append("PIPEFY_SERVICE_ACCOUNT_*")
    elif all(os.environ.get(k) for k in _LEGACY_SERVICE_ACCOUNT_ENV_KEYS):
        env_vars.append("PIPEFY_OAUTH_*")
    return env_vars


def _warn_if_masked() -> None:
    env_vars = _session_masking_env_vars()
    if not env_vars:
        return
    typer.echo(
        f"Note: {', '.join(env_vars)} is set in your environment; other `pipefy` "
        "commands will continue to use it until you unset it.",
        err=True,
    )


@auth_app.command("login")
def auth_login(
    ctx: typer.Context,
    no_browser: bool = typer.Option(  # noqa: B008 (Typer Option pattern)
        False,
        "--no-browser",
        help="Print the authorization URL instead of opening a browser.",
    ),
    callback_timeout: float = typer.Option(  # noqa: B008
        180.0,
        "--callback-timeout",
        help="Seconds to wait for the browser callback before giving up.",
        min=5.0,
    ),
) -> None:
    """Sign in to Pipefy via your browser and store the session in the OS keychain."""
    # Lazy to keep keyring's ~30-80ms backend-discovery cost off every CLI startup.
    from keyring.errors import KeyringError

    settings, auth = settings_and_auth_from_ctx(ctx)
    if auth.oidc_client is None:
        typer.echo(
            "Stored sessions are disabled (PIPEFY_DISABLE_STORED_SESSION=1 or "
            "disable_stored_session=true in config.toml). Unset to log in, or "
            "use PIPEFY_TOKEN / PIPEFY_SERVICE_ACCOUNT_* for non-interactive auth.",
            err=True,
        )
        raise typer.Exit(2)
    issuer_url = auth.oidc_client.issuer_url
    client_id = auth.oidc_client.client_id
    typer.echo(f"Signing in to Pipefy at {issuer_url} ...")

    def _print_url(url: str) -> None:
        typer.echo(f"\nAuthorization URL: {url}\n")

    def _open(url: str) -> bool:
        if no_browser:
            return False
        if webbrowser.open(url):
            return True
        typer.echo(
            "Could not open a browser automatically. Open the URL below, or "
            "re-run with --no-browser.",
            err=True,
        )
        return False

    try:
        result = run_login(
            issuer_url=issuer_url,
            client_id=client_id,
            callback_timeout_s=callback_timeout,
            open_browser=_open,
            on_url=_print_url,
            discovery_policy=DiscoveryPolicy(
                allow_insecure_urls=settings.allow_insecure_urls
            ),
        )
    except LoginError as exc:
        typer.echo(f"Login failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    except TimeoutError as exc:
        typer.echo(f"Login timed out: {exc}", err=True)
        raise typer.Exit(1) from exc
    except KeyboardInterrupt:
        typer.echo("Login cancelled.", err=True)
        raise typer.Exit(130) from None

    try:
        store_session(
            issuer=result.issuer,
            client_id=client_id,
            token=result.token,
        )
    except (KeyringError, OSError) as exc:
        # ``OSError`` covers the file-backed PlaintextKeyring path: a read-only
        # ``config_dir()`` (e.g. CI runner without write perms, NFS mount
        # without ownership) surfaces as ``PermissionError`` from
        # ``os.makedirs`` inside the backend, which is not a ``KeyringError``.
        backend = keychain_backend_name()
        if backend == "PlaintextKeyring":
            from pipefy_infra.config import config_dir

            hint = (
                f"Ensure the config directory is writable ({config_dir()}), "
                "or use a static PIPEFY_TOKEN."
            )
        else:
            hint = (
                "On headless Linux, ensure a Secret Service daemon "
                "(gnome-keyring, kwallet) is running, set "
                "PIPEFY_KEYCHAIN_BACKEND=file to use a plaintext file backend, "
                "or use a static PIPEFY_TOKEN."
            )
        typer.echo(
            f"Login succeeded but the session could not be stored in your "
            f"keychain ({backend}): {exc}. {hint}",
            err=True,
        )
        raise typer.Exit(1) from exc

    typer.echo(
        f"Signed in to Pipefy ({result.issuer}). Session stored in {keychain_backend_name()}."
    )
    _warn_if_masked()


_AUTH_SOURCE_LABELS: dict[DisplaySource, str] = {
    "flag-token": "--token flag",
    "env-token": "PIPEFY_TOKEN environment variable",
    "service-account": "PIPEFY_SERVICE_ACCOUNT_* (client credentials)",
    "stored-session": "stored session (`pipefy auth login`)",
    "none": "none",
}


def _iso_expiry(obtained_at: int, lifetime_s: int | None) -> str | None:
    """Compute the ISO 8601 expiry timestamp; ``None`` when ``lifetime_s`` is missing."""
    if lifetime_s is None:
        return None
    return (
        datetime.fromtimestamp(obtained_at + lifetime_s, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _format_relative(iso_ts: str | None) -> str:
    """Render an ISO timestamp as a human-friendly "in 4h 12m" / "expired" string."""
    if iso_ts is None:
        return "unknown"
    target = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    delta = target - datetime.now(tz=timezone.utc)
    seconds = int(delta.total_seconds())
    if seconds <= 0:
        return "expired"
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return f"in {days}d {hours}h"
    return f"in {hours}h {minutes}m"


def _to_json_payload(report: AuthStatusReport) -> dict[str, Any]:
    """Serialize the report to the locked JSON wire schema."""
    return {
        "signed_in": report.signed_in,
        "identity": report.identity,
        "auth_source": report.auth_source,
        "detected_sources": report.detected_sources,
        "issuer": report.issuer,
        "state": report.state,
        "access_expires_at": report.access_expires_at,
        "refresh_expires_at": report.refresh_expires_at,
        "token_rejected": report.token_rejected,
        "keychain_backend": report.keychain_backend,
        "masking_env_vars": report.masking_env_vars,
    }


def _render_status_text(report: AuthStatusReport) -> None:
    """Human-readable rendering of the status report (stdout)."""
    if not report.signed_in:
        typer.echo(
            "Not signed in. Run `pipefy auth login`, set PIPEFY_TOKEN, or "
            f"configure PIPEFY_SERVICE_ACCOUNT_*. See {DOCS_CLI_AUTH_REF}."
        )
        return

    header = (
        f"Signed in to Pipefy ({report.issuer})"
        if report.issuer
        else "Signed in to Pipefy"
    )
    typer.echo(header)

    if report.identity is not None:
        email = report.identity["email"]
        name = report.identity.get("name")
        identity_label = f"{email} ({name})" if name else email
        typer.echo(f"  Identity:      {identity_label}")
    elif report.token_rejected:
        typer.echo("  Identity:      unknown (token rejected by upstream)")
    else:
        typer.echo("  Identity:      unknown")

    typer.echo(f"  Auth source:   {_AUTH_SOURCE_LABELS[report.auth_source]}")

    if report.auth_source == "stored-session":
        typer.echo(f"  Expires:       {_format_relative(report.access_expires_at)}")
        typer.echo(f"  Refresh token: {_format_relative(report.refresh_expires_at)}")
        if report.keychain_backend:
            typer.echo(f"  Keychain:      {report.keychain_backend}")

    if report.masking_env_vars:
        typer.echo("")
        typer.echo("Other auth sources detected in env:")
        for name in report.masking_env_vars:
            typer.echo(
                f"  {name} (would mask the stored session if no --token is passed)"
            )


def _render(report: AuthStatusReport, *, json_out: bool) -> None:
    """Render the report on stdout in the requested format."""
    if json_out:
        render_json(_to_json_payload(report))
    else:
        _render_status_text(report)


@dataclass
class _StatusExit(Exception):
    """Control-flow signal raised by phase helpers; translated to ``typer.Exit`` at the command boundary.

    Carries the report (which may differ from the in-progress one — see the vanished-session
    branch) along with the exit code and optional stderr message.
    """

    report: AuthStatusReport
    exit_code: int
    stderr: str | None = None


def _populate_stored_session(report: AuthStatusReport, oidc: OidcClient) -> None:
    """Populate stored-session fields on ``report``; raise ``_StatusExit`` on failure."""
    report.issuer = oidc.issuer_url
    report.keychain_backend = keychain_backend_name()
    try:
        fresh_session = ensure_fresh_session(
            issuer=oidc.issuer_url, client_id=oidc.client_id
        )
    except RefreshError as exc:
        # Branch on the RFC 6749 ``error`` field, not on ``str(exc)``. The
        # message text is for humans; ``error_code`` is the machine contract.
        report.state = (
            "refresh-expired" if exc.error_code == "invalid_grant" else "needs-login"
        )
        # Best-effort expiry from the pre-refresh blob so users see *why*.
        stale = load_session(issuer=oidc.issuer_url, client_id=oidc.client_id)
        if stale is not None:
            report.access_expires_at = _iso_expiry(
                stale.obtained_at, stale.token.expires_in
            )
            # refresh_expires_in: 0 is Keycloak's "no advertised expiry" sentinel,
            # not a 0-second TTL — treat as no expiry (else it renders "expired").
            report.refresh_expires_at = _iso_expiry(
                stale.obtained_at, stale.token.refresh_expires_in or None
            )
        raise _StatusExit(
            report=report,
            exit_code=2,
            stderr=(
                f"Stored Pipefy session could not be refreshed: {exc}. "
                "Run `pipefy auth login` to sign in again."
            ),
        ) from exc
    if fresh_session is None:
        # Session vanished between detection and refresh.
        raise _StatusExit(
            report=AuthStatusReport(
                auth_source="none", detected_sources=report.detected_sources
            ),
            exit_code=2,
        )
    report.state = "active"
    report.access_expires_at = _iso_expiry(
        fresh_session.obtained_at, fresh_session.token.expires_in
    )
    report.refresh_expires_at = _iso_expiry(
        fresh_session.obtained_at, fresh_session.token.refresh_expires_in or None
    )


def _fetch_identity(
    report: AuthStatusReport, settings: PipefySettings, auth: AuthContext
) -> None:
    """Populate ``report.identity``; raise ``_StatusExit`` on transport / 401."""
    client = get_authenticated_client(settings, auth)
    try:
        report.identity = asyncio.run(client.get_me())
    except TransportServerError as exc:
        # Pipefy returns a literal HTTP 401 for invalid bearers (verified via
        # `curl -X POST <graphql>` with a bad token); other HTTP errors here
        # are upstream/transport problems, not credential rejections.
        if exc.code == 401:
            report.token_rejected = True
        raise _StatusExit(
            report=report, exit_code=1, stderr=f"Identity fetch failed: {exc}"
        ) from exc
    except (TransportQueryError, TransportError) as exc:
        raise _StatusExit(
            report=report, exit_code=1, stderr=f"Pipefy transport error: {exc}"
        ) from exc


@auth_app.command("status")
def auth_status(
    ctx: typer.Context,
    json_out: bool = typer.Option(  # noqa: B008 (Typer Option pattern)
        False,
        "--json",
        "-j",
        help="Emit a stable JSON schema instead of human-readable text.",
    ),
) -> None:
    """Print which auth source is active, the authenticated identity, and session expiry."""
    settings, auth = settings_and_auth_from_ctx(ctx)
    auth_methods = detect_cli_auth_methods(auth)
    detected_sources: list[DisplaySource] = [
        to_display_source(method, auth.bearer_token) for method in auth_methods
    ]
    # Precedence-first, so the head is the active method and the same winner the
    # resolver would pick, without a second resolve pass.
    active = auth_methods[0] if auth_methods else None
    source: DisplaySource = (
        to_display_source(active, auth.bearer_token) if active else "none"
    )
    report = AuthStatusReport(auth_source=source, detected_sources=detected_sources)
    # Surface masking env vars whenever a stored session exists: that's the
    # CI-overrides-keychain failure mode the field is for, and the higher-
    # precedence winner is the case where it matters.
    if any(isinstance(method, StoredSessionAuth) for method in auth_methods):
        report.masking_env_vars = _session_masking_env_vars()

    try:
        if active is None:
            raise _StatusExit(report=report, exit_code=2)
        # A StoredSessionAuth carries its OIDC client by construction, so
        # populating session details needs no presence check.
        if isinstance(active, StoredSessionAuth):
            _populate_stored_session(report, active.oidc_client)
        _fetch_identity(report, settings, auth)
    except _StatusExit as exit_:
        _render(exit_.report, json_out=json_out)
        if exit_.stderr and not json_out:
            typer.echo(exit_.stderr, err=True)
        raise typer.Exit(exit_.exit_code) from exit_

    _render(report, json_out=json_out)


@auth_app.command("logout")
def auth_logout(ctx: typer.Context) -> None:
    """Revoke the stored refresh token at the IdP and clear the local session."""
    settings, auth = settings_and_auth_from_ctx(ctx)
    if auth.oidc_client is None:
        typer.echo(
            "Stored sessions are disabled (PIPEFY_DISABLE_STORED_SESSION=1 or "
            "disable_stored_session=true in config.toml). Nothing to do.",
            err=True,
        )
        raise typer.Exit(2)
    issuer = auth.oidc_client.issuer_url
    client_id = auth.oidc_client.client_id

    session = load_session(issuer=issuer, client_id=client_id)
    if session is None:
        typer.echo("Not signed in. Nothing to do.")
        return

    # Revoke at the IdP first — once we delete the keychain entry we no longer
    # have the refresh_token to send. On any revoke failure still proceed to
    # delete (warning makes the difference honest: server-side credential may
    # remain valid until natural expiry).
    revoke_warning: str | None = None
    try:
        revoke_session(
            issuer=issuer,
            client_id=client_id,
            refresh_token=session.token.refresh_token,
            policy=DiscoveryPolicy(allow_insecure_urls=settings.allow_insecure_urls),
        )
    except RevocationUnsupportedError:
        revoke_warning = (
            "Pipefy auth server does not advertise a logout endpoint; the "
            "refresh token could not be revoked server-side. Clearing local "
            "session only."
        )
    except RevocationError as exc:
        revoke_warning = (
            f"Could not revoke refresh token at the IdP: {exc}. Clearing "
            "local session anyway; the refresh token may remain valid at the "
            "server until natural expiry."
        )

    try:
        delete_session(issuer=issuer, client_id=client_id)
    except SessionDeleteError as exc:
        if revoke_warning:
            typer.echo(revoke_warning, err=True)
        typer.echo(
            f"Could not delete local session from the keychain: {exc}. "
            "The stored credential may still be present; remove it manually "
            f"via your OS keychain (service: 'pipefy'). See {DOCS_CLI_AUTH_REF}.",
            err=True,
        )
        raise typer.Exit(1) from exc

    if revoke_warning:
        typer.echo(revoke_warning, err=True)
    typer.echo(f"Signed out of Pipefy ({issuer}).")


__all__ = ["auth_app"]
