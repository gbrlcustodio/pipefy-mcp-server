"""Interactive user authentication via OAuth 2.0 Authorization Code + PKCE."""

from __future__ import annotations

import os

import typer
from keyring.errors import KeyringError

from pipefy_cli._docs import DOCS_SETUP_REF
from pipefy_cli.config import DEFAULT_AUTH_CLIENT_ID, CliSettings
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

_MASKING_ENV_KEYS = ("PIPEFY_TOKEN", "PIPEFY_OAUTH_URL", "PIPEFY_OAUTH_CLIENT")


def _resolve_auth_config() -> tuple[str, str]:
    """Return ``(auth_url, client_id)`` or raise typer.Exit(2) with guidance."""
    try:
        settings = CliSettings()
    except Exception as exc:  # pydantic ValidationError or env parsing failure
        typer.echo(f"Could not load CLI settings: {exc}", err=True)
        raise typer.Exit(2) from exc

    auth_url = (settings.auth_url or "").strip()
    if not auth_url:
        typer.echo(
            "PIPEFY_AUTH_URL is required for `pipefy auth login` (the OIDC issuer URL "
            "for Pipefy authentication, e.g. "
            "https://signin.pipefy.com/realms/pipefy). "
            f"See {DOCS_SETUP_REF}.",
            err=True,
        )
        raise typer.Exit(2)
    client_id = (settings.auth_client_id or DEFAULT_AUTH_CLIENT_ID).strip()
    return auth_url, client_id


def _warn_if_masked() -> None:
    """Warn if any shell env var would mask the stored session (gh-style)."""
    set_keys = [key for key in _MASKING_ENV_KEYS if os.environ.get(key)]
    if not set_keys:
        return
    typer.echo(
        "Note: "
        + ", ".join(set_keys)
        + " is set in your environment; the CLI will use it instead of this login "
        "session until you unset it.",
        err=True,
    )


@auth_app.command("login")
def auth_login(
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
    auth_url, client_id = _resolve_auth_config()
    typer.echo(f"Signing in to Pipefy at {auth_url} ...")

    def _print_url(url: str) -> None:
        typer.echo(f"\nAuthorization URL: {url}\n")

    def _open(url: str) -> bool:
        if no_browser:
            return False
        import webbrowser

        return webbrowser.open(url)

    try:
        result = run_login(
            issuer_url=auth_url,
            client_id=client_id,
            callback_timeout_s=callback_timeout,
            open_browser=_open,
            on_url=_print_url if no_browser else None,
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
    except KeyringError as exc:
        typer.echo(
            f"Login succeeded but the session could not be stored in your OS "
            f"keychain ({keychain_backend_name()}): {exc}. "
            "On headless Linux, ensure a Secret Service daemon (gnome-keyring, "
            "kwallet) is running, or use a static PIPEFY_TOKEN.",
            err=True,
        )
        raise typer.Exit(1) from exc
    except ValueError as exc:
        typer.echo(
            f"Login succeeded but the token response was malformed: {exc}", err=True
        )
        raise typer.Exit(1) from exc

    if "refresh_token" not in result.token_response:
        # Defensive: store_session raises ValueError above when missing, so this
        # branch is unreachable in practice. Kept as a belt-and-suspenders note.
        typer.echo(
            "Warning: the auth server did not issue a refresh token. You will need "
            "to log in again when the access token expires (~5 min).",
            err=True,
        )

    typer.echo(
        f"Signed in to Pipefy ({result.issuer}). Session stored in {keychain_backend_name()}."
    )
    _warn_if_masked()


__all__ = ["auth_app"]
