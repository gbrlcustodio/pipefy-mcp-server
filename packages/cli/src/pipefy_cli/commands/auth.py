"""Interactive user authentication via OAuth 2.0 Authorization Code + PKCE."""

from __future__ import annotations

import asyncio
import os
import webbrowser
from datetime import datetime, timezone
from typing import Any, Literal

import typer
from gql.transport.exceptions import (
    TransportError,
    TransportQueryError,
    TransportServerError,
)

from pipefy_cli._docs import DOCS_CLI_AUTH_REF
from pipefy_cli.auth import (
    AuthSource,
    detect_all_sources,
    get_authenticated_client,
)
from pipefy_cli.commands._common import settings_and_auth_from_ctx
from pipefy_cli.oauth import (
    LoginError,
    RefreshError,
    ensure_fresh_session,
    keychain_backend_name,
    load_session,
    run_login,
    store_session,
)
from pipefy_cli.output import render_json

AuthSessionState = Literal["active", "refresh-expired", "needs-login", "n/a"]

auth_app = typer.Typer(
    help="Authenticate the CLI as your Pipefy user (browser-based login).",
    no_args_is_help=True,
)

_SERVICE_ACCOUNT_ENV_KEYS = (
    "PIPEFY_OAUTH_URL",
    "PIPEFY_OAUTH_CLIENT",
    "PIPEFY_OAUTH_SECRET",
)


def _session_masking_env_vars() -> list[str]:
    """Env vars that outrank a stored session in the credential precedence chain.

    Only ``os.environ`` is consulted — by the precedence model, ``.env`` defaults
    sit below the stored session. ``PIPEFY_OAUTH_*`` is listed only when the
    *complete* triple is configured (otherwise the client-credentials path
    wouldn't activate and the warning would be misleading).
    """
    env_vars: list[str] = []
    if os.environ.get("PIPEFY_TOKEN"):
        env_vars.append("PIPEFY_TOKEN")
    if all(os.environ.get(k) for k in _SERVICE_ACCOUNT_ENV_KEYS):
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

    _, auth = settings_and_auth_from_ctx(ctx)
    if auth.oidc_client is None:
        typer.echo(
            "PIPEFY_AUTH_URL is required for `pipefy auth login` (the OIDC issuer "
            "URL for Pipefy authentication, e.g. "
            "https://signin.pipefy.com/realms/pipefy). "
            f"See {DOCS_CLI_AUTH_REF}.",
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
            token_response=result.token_response,
        )
    except ValueError as exc:
        typer.echo(
            f"Login succeeded but the token response was malformed: {exc}", err=True
        )
        raise typer.Exit(1) from exc
    except KeyringError as exc:
        typer.echo(
            f"Login succeeded but the session could not be stored in your OS "
            f"keychain ({keychain_backend_name()}): {exc}. "
            "On headless Linux, ensure a Secret Service daemon (gnome-keyring, "
            "kwallet) is running, or use a static PIPEFY_TOKEN.",
            err=True,
        )
        raise typer.Exit(1) from exc

    typer.echo(
        f"Signed in to Pipefy ({result.issuer}). Session stored in {keychain_backend_name()}."
    )
    _warn_if_masked()


_AUTH_SOURCE_LABELS: dict[AuthSource, str] = {
    "flag-token": "--token flag",
    "env-token": "PIPEFY_TOKEN environment variable",
    "service-account": "PIPEFY_OAUTH_* (client credentials)",
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


def _render_status_text(payload: dict[str, Any]) -> None:
    """Human-readable rendering of the status payload (stdout)."""
    source: AuthSource = payload["auth_source"]
    if not payload["signed_in"]:
        typer.echo(
            "Not signed in. Run `pipefy auth login`, set PIPEFY_TOKEN, or "
            f"configure PIPEFY_OAUTH_*. See {DOCS_CLI_AUTH_REF}."
        )
        return

    issuer = payload["issuer"]
    header = f"Signed in to Pipefy ({issuer})" if issuer else "Signed in to Pipefy"
    typer.echo(header)

    identity = payload["identity"]
    if identity is not None:
        if identity.get("name"):
            typer.echo(f"  Identity:      {identity['email']} ({identity['name']})")
        else:
            typer.echo(f"  Identity:      {identity['email']}")
    elif payload["token_rejected"]:
        typer.echo("  Identity:      unknown (token rejected by upstream)")
    else:
        typer.echo("  Identity:      unknown")

    typer.echo(f"  Auth source:   {_AUTH_SOURCE_LABELS[source]}")

    if source == "stored-session":
        typer.echo(f"  Expires:       {_format_relative(payload['access_expires_at'])}")
        typer.echo(
            f"  Refresh token: {_format_relative(payload['refresh_expires_at'])}"
        )
        if payload["keychain_backend"]:
            typer.echo(f"  Keychain:      {payload['keychain_backend']}")

    masking = payload["masking_env_vars"]
    if masking:
        typer.echo("")
        typer.echo("Other auth sources detected in env:")
        for name in masking:
            typer.echo(
                f"  {name} (would mask the stored session if no --token is passed)"
            )


def _emit_and_exit(
    payload: dict[str, Any],
    *,
    json_out: bool,
    exit_code: int,
    stderr: str | None = None,
) -> typer.Exit:
    """Render ``payload`` (JSON or text) and return the ``Exit`` for the caller to raise."""
    if json_out:
        render_json(payload)
    else:
        _render_status_text(payload)
        if stderr:
            typer.echo(stderr, err=True)
    return typer.Exit(exit_code)


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
    detected = detect_all_sources(settings, auth)
    source: AuthSource = detected[0] if detected else "none"

    payload: dict[str, Any] = {
        "signed_in": source != "none",
        "identity": None,
        "auth_source": source,
        "detected_sources": detected,
        "issuer": None,
        "state": "n/a",
        "access_expires_at": None,
        "refresh_expires_at": None,
        "token_rejected": False,
        "keychain_backend": None,
        "masking_env_vars": [],
    }

    if source == "none":
        raise _emit_and_exit(payload, json_out=json_out, exit_code=2)

    if source == "stored-session":
        assert auth.oidc_client is not None
        payload["issuer"] = auth.oidc_client.issuer_url
        payload["keychain_backend"] = keychain_backend_name()
        payload["masking_env_vars"] = _session_masking_env_vars()
        try:
            fresh_session = ensure_fresh_session(
                issuer=auth.oidc_client.issuer_url,
                client_id=auth.oidc_client.client_id,
            )
        except RefreshError as exc:
            state: AuthSessionState = (
                "refresh-expired" if "invalid_grant" in str(exc) else "needs-login"
            )
            payload["state"] = state
            # Best-effort expiry from the pre-refresh blob so users see *why*.
            stale = load_session(
                issuer=auth.oidc_client.issuer_url,
                client_id=auth.oidc_client.client_id,
            )
            if stale is not None:
                payload["access_expires_at"] = _iso_expiry(
                    stale.obtained_at, stale.expires_in
                )
                payload["refresh_expires_at"] = _iso_expiry(
                    stale.obtained_at, stale.refresh_expires_in
                )
            raise _emit_and_exit(
                payload,
                json_out=json_out,
                exit_code=2,
                stderr=(
                    f"Stored Pipefy session could not be refreshed: {exc}. "
                    "Run `pipefy auth login` to sign in again."
                ),
            ) from exc
        if fresh_session is None:
            # Vanished between detection and refresh.
            payload["signed_in"] = False
            payload["auth_source"] = "none"
            raise _emit_and_exit(payload, json_out=json_out, exit_code=2)
        payload["state"] = "active"
        payload["access_expires_at"] = _iso_expiry(
            fresh_session.obtained_at, fresh_session.expires_in
        )
        payload["refresh_expires_at"] = _iso_expiry(
            fresh_session.obtained_at, fresh_session.refresh_expires_in
        )

    client = get_authenticated_client(settings, auth)
    try:
        payload["identity"] = asyncio.run(client.get_me())
    except TransportServerError as exc:
        # Pipefy returns a literal HTTP 401 for invalid bearers (verified via
        # `curl -X POST <graphql>` with a bad token); other HTTP errors here
        # are upstream/transport problems, not credential rejections.
        if exc.code == 401:
            payload["token_rejected"] = True
        raise _emit_and_exit(
            payload,
            json_out=json_out,
            exit_code=1,
            stderr=f"Identity fetch failed: {exc}",
        ) from exc
    except (TransportQueryError, TransportError) as exc:
        raise _emit_and_exit(
            payload,
            json_out=json_out,
            exit_code=1,
            stderr=f"Pipefy transport error: {exc}",
        ) from exc

    if json_out:
        render_json(payload)
    else:
        _render_status_text(payload)


__all__ = ["auth_app"]
