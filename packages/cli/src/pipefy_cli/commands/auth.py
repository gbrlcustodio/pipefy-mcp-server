"""Interactive user authentication via OAuth 2.0 Authorization Code + PKCE."""

from __future__ import annotations

import os
import webbrowser

import typer

from pipefy_cli._docs import DOCS_SETUP_REF
from pipefy_cli.oauth import (
    LoginError,
    keychain_backend_name,
    run_login,
    store_session,
)

auth_app = typer.Typer(
    help="Authenticate the CLI as your Pipefy user (browser-based login).",
    no_args_is_help=True,
)

_SERVICE_ACCOUNT_ENV_KEYS = (
    "PIPEFY_OAUTH_URL",
    "PIPEFY_OAUTH_CLIENT",
    "PIPEFY_OAUTH_SECRET",
)


def _auth_config_from_ctx(ctx: typer.Context) -> tuple[str, str]:
    """Return ``(auth_url, client_id)`` from the root callback's stash.

    Raises ``typer.Exit(2)`` when ``PIPEFY_AUTH_URL`` is unset.
    """
    obj = ctx.find_root().obj
    auth_url = obj.get("auth_url") or ""
    if not auth_url:
        typer.echo(
            "PIPEFY_AUTH_URL is required for `pipefy auth login` (the OIDC issuer "
            "URL for Pipefy authentication, e.g. "
            "https://signin.pipefy.com/realms/pipefy). "
            f"See {DOCS_SETUP_REF}.",
            err=True,
        )
        raise typer.Exit(2)
    return auth_url, obj["auth_client_id"]


def _active_masking_sources() -> list[str]:
    """Env vars that outrank a stored session in the credential precedence chain.

    Only ``os.environ`` is consulted — by the precedence model, ``.env`` defaults
    sit below the stored session. ``PIPEFY_OAUTH_*`` is listed only when the
    *complete* triple is configured (otherwise the client-credentials path
    wouldn't activate and the warning would be misleading).
    """
    sources: list[str] = []
    if os.environ.get("PIPEFY_TOKEN"):
        sources.append("PIPEFY_TOKEN")
    if all(os.environ.get(k) for k in _SERVICE_ACCOUNT_ENV_KEYS):
        sources.append("PIPEFY_OAUTH_*")
    return sources


def _warn_if_masked() -> None:
    sources = _active_masking_sources()
    if not sources:
        return
    typer.echo(
        f"Note: {', '.join(sources)} is set in your environment; other `pipefy` "
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

    auth_url, client_id = _auth_config_from_ctx(ctx)
    typer.echo(f"Signing in to Pipefy at {auth_url} ...")

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
            issuer_url=auth_url,
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


__all__ = ["auth_app"]
