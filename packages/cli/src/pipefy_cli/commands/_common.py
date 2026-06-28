"""Shared Typer helpers for domain command modules."""

from __future__ import annotations

import asyncio
import json
import math
import sys
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import typer
from gql.transport.exceptions import TransportError, TransportQueryError
from pipefy_sdk import PipefyClient, PipefySettings, stream_bytes
from pipefy_sdk.exceptions import PipefyError
from pipefy_sdk.label_color import normalize_label_color
from pipefy_sdk.report_filter_preflight import prepare_report_cards_filter

from pipefy_cli.auth import (
    AuthContext,
    BearerToken,
    get_authenticated_client,
)
from pipefy_cli.output import render_json, render_rich

_T = TypeVar("_T")
_R = TypeVar("_R")

DEFAULT_EXPORT_MAX_BYTES = 50 * 1024 * 1024

# Pipefy occasionally encodes ids with a leading hyphen (e.g. table id "-ZocGcM0").
# Click parses tokens starting with "-" as short options by default, which breaks
# every `<sub> get/update/delete <ID>` command. Setting ignore_unknown_options on
# the command relaxes the parser so the dashed token is consumed as the positional
# id. Tokens starting with ``--`` must still be rejected (they look like long
# options); use :func:`validate_positional_id` on those arguments.
ID_POSITIONAL_CONTEXT_SETTINGS = {"ignore_unknown_options": True}


def validate_positional_id(value: str) -> str:
    """Reject typoed long-option tokens mistakenly captured as a resource id."""
    if value.startswith("--"):
        raise typer.BadParameter(
            f"unknown option-like value {value!r}; if an id starts with '-', pass it after '--'"
        )
    return value


def resource_id_argument(*, help: str) -> Any:
    """Typer ``Argument`` for resource ids when ``ignore_unknown_options`` is enabled."""
    return typer.Argument(..., help=help, callback=validate_positional_id)


def validate_optional_resource_id(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise typer.BadParameter(
            f"Invalid '{label}': provide a non-empty string or positive integer."
        )
    if cleaned.startswith("-") and cleaned[1:].isdigit():
        raise typer.BadParameter(f"Invalid '{label}': provide a positive integer.")
    if cleaned.isdigit() and int(cleaned) <= 0:
        raise typer.BadParameter(f"Invalid '{label}': provide a positive integer.")
    return cleaned


_CARDS_PAGE_SIZE_MIN = 1
_CARDS_PAGE_SIZE_MAX = 500


def validate_cards_page_size(first: int | None) -> int | None:
    if first is None:
        return None
    if first < _CARDS_PAGE_SIZE_MIN or first > _CARDS_PAGE_SIZE_MAX:
        raise typer.BadParameter(
            f"--first must be between {_CARDS_PAGE_SIZE_MIN} and "
            f"{_CARDS_PAGE_SIZE_MAX} (inclusive)."
        )
    return first


def validate_label_name_cli(name: str) -> str:
    nm = name.strip()
    if not nm:
        raise typer.BadParameter("--name must be non-empty.")
    return nm


def prepare_report_cards_filter_cli(
    filter_obj: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Normalize and validate ``ReportCardsFilter`` before auth or network I/O."""
    try:
        return prepare_report_cards_filter(filter_obj)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def normalize_label_color_cli(color: str) -> str:
    """Normalize label ``color`` before auth or network I/O."""
    try:
        return normalize_label_color(color)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def export_poll_max_rounds(
    poll_timeout_seconds: float, *, delay_seconds: float = 2.0
) -> int:
    """Map a wall-clock export poll budget to loop iterations (``delay_seconds`` per round).

    Args:
        poll_timeout_seconds: Maximum time to wait for export state ``done``.
        delay_seconds: Sleep between status polls.
    """
    if poll_timeout_seconds <= 0:
        raise ValueError("poll_timeout_seconds must be positive")
    return max(1, math.ceil(poll_timeout_seconds / delay_seconds))


async def poll_export_until_done(
    fetch: Callable[[str], Awaitable[dict[str, Any] | None]],
    export_id: str,
    unwrap: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    max_rounds: int,
    delay_seconds: float = 2.0,
) -> str:
    """Poll an export job until ``state == done`` and return ``fileURL``.

    Args:
        fetch: Async callable taking export id and returning the raw GraphQL payload dict.
        export_id: Export job id from the start mutation.
        unwrap: Extract the export status node dict from ``fetch``'s return value.
        max_rounds: Maximum poll iterations before timing out.
        delay_seconds: Delay between polls.
    """
    eid = str(export_id)
    for _ in range(max_rounds):
        raw = await fetch(eid)
        node = unwrap(raw or {}) or {}
        state = str(node.get("state") or "")
        if state in ("failed", "error"):
            raise ValueError(f"Export failed (state={state!r}).")
        if state == "done":
            url = node.get("fileURL") or node.get("fileUrl")
            if isinstance(url, str) and url.strip():
                return url.strip()
            raise ValueError("Export is done but fileURL is missing.")
        await asyncio.sleep(delay_seconds)
    raise ValueError(
        f"Timed out waiting for export {eid} after {max_rounds * delay_seconds:.0f}s."
    )


async def write_export_csv_to_stdout(
    *,
    export_id: str,
    poll_fetch: Callable[[str], Awaitable[dict[str, Any] | None]],
    unwrap_status: Callable[[dict[str, Any]], dict[str, Any]],
    poll_timeout_seconds: float,
    max_bytes: int = DEFAULT_EXPORT_MAX_BYTES,
) -> None:
    """Poll an export job until ``done`` and stream the CSV body to stdout.

    Args:
        export_id: Export job id (from the start mutation).
        poll_fetch: Async callable that fetches the export status payload by id.
        unwrap_status: Extract the export status node dict from the raw payload.
        poll_timeout_seconds: Wall-clock budget for polling before raising ``ValueError``.
        max_bytes: Hard cap on the download size enforced by :func:`stream_bytes`.
    """
    max_rounds = export_poll_max_rounds(poll_timeout_seconds)
    url = await poll_export_until_done(
        poll_fetch,
        export_id,
        unwrap_status,
        max_rounds=max_rounds,
    )
    async for chunk in stream_bytes(url, max_bytes=max_bytes):
        sys.stdout.buffer.write(chunk)
    sys.stdout.buffer.flush()


def run_pipefy_client_coroutine(
    ctx: typer.Context,
    coro_factory: Callable[[PipefyClient], Awaitable[_T]],
    *,
    value_error_exit_code: int | None = None,
) -> _T:
    """Run ``asyncio.run`` on a coroutine built with a configured :class:`PipefyClient`.

    Args:
        ctx: Typer context (resolves settings/token from the root app).
        coro_factory: Async callable receiving an authenticated client.
        value_error_exit_code: When set, map ``ValueError`` from the factory to this exit code (stderr message).

    Returns:
        The coroutine result.

    Raises:
        typer.Exit: On :class:`PipefyError` (exit code 1), optional ``ValueError`` mapping, or ``BrokenPipeError`` (exit 0).
    """
    pipefy_settings, auth = settings_and_auth_from_ctx(ctx)

    async def _run() -> _T:
        client = get_authenticated_client(pipefy_settings, auth)
        return await coro_factory(client)

    try:
        return asyncio.run(_run())
    except PipefyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    except ValueError as exc:
        if value_error_exit_code is None:
            raise
        typer.echo(str(exc), err=True)
        raise typer.Exit(value_error_exit_code) from exc
    except BrokenPipeError:
        raise typer.Exit(0) from None
    except TransportQueryError as exc:
        typer.echo(_format_transport_query_error(exc), err=True)
        raise typer.Exit(1) from exc
    except TransportError as exc:
        typer.echo(f"Pipefy transport error: {exc}", err=True)
        raise typer.Exit(1) from exc


def _format_transport_query_error(exc: TransportQueryError) -> str:
    """Render a GraphQL transport error as a clean single-line message for the CLI.

    Falls back to ``str(exc)`` when the structured ``errors`` payload is missing or empty.
    """
    errors = getattr(exc, "errors", None) or []
    if not errors:
        return str(exc)
    first = errors[0] if isinstance(errors[0], dict) else {"message": str(errors[0])}
    message = first.get("message") or str(exc)
    code = (first.get("extensions") or {}).get("code")
    return f"{message} ({code})" if code else message


def format_card_get_transport_query_error(exc: TransportQueryError) -> str:
    """Like :func:`_format_transport_query_error` with a hint for missing/deleted cards."""
    base = _format_transport_query_error(exc)
    errors = getattr(exc, "errors", None) or []
    if errors and isinstance(errors[0], dict):
        code = (errors[0].get("extensions") or {}).get("code")
        if code == "PERMISSION_DENIED":
            return f"{base} The card may have been deleted or is not visible to this token."
    return base


def settings_and_token(
    ctx: typer.Context,
) -> tuple[PipefySettings, BearerToken | None]:
    """Resolve root CLI context object into settings and optional bearer token."""
    root = ctx.find_root()
    obj = root.obj
    return obj["pipefy_settings"], obj.get("token")


def org_id_from_ctx(ctx: typer.Context) -> str | None:
    """The default organization id resolved at the CLI edge (env: PIPEFY_ORG_ID)."""
    return ctx.find_root().obj.get("org_id")


def settings_and_auth_from_ctx(
    ctx: typer.Context,
) -> tuple[PipefySettings, AuthContext]:
    """Resolve root ``ctx.obj`` into the (settings, auth) pair the client boundary needs."""
    obj = ctx.find_root().obj
    auth_settings = obj["auth_settings"]
    auth = AuthContext(
        bearer_token=obj.get("token"),
        service_account=auth_settings.to_service_account(),
        oidc_client=auth_settings.to_oidc_client(),
    )
    return obj["pipefy_settings"], auth


def authenticated_client_from_ctx(ctx: typer.Context) -> PipefyClient:
    """Build a :class:`PipefyClient` using the same auth path as ``run_cli_command``."""
    pipefy_settings, auth = settings_and_auth_from_ctx(ctx)
    return get_authenticated_client(pipefy_settings, auth)


def parse_json_value(raw: str | None, option_name: str) -> Any:
    """Parse a JSON value from a CLI string option (empty input returns ``None``)."""
    if raw is None or raw.strip() == "":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON for {option_name}: {exc}") from exc


def parse_json_object(raw: str | None, option_name: str) -> dict[str, Any] | None:
    """Parse a JSON object from a CLI string option (empty input returns ``None``)."""
    if raw is None or raw.strip() == "":
        return None
    parsed = parse_json_value(raw, option_name)
    if not isinstance(parsed, dict):
        raise typer.BadParameter(f"{option_name} must be a JSON object")
    return parsed


def confirm_destructive(*, yes: bool, description: str, verb: str = "delete") -> None:
    """Prompt before a destructive action unless ``yes`` is True."""
    if yes:
        return
    if not typer.confirm(f"Permanently {verb} {description}?"):
        raise typer.Abort()


def run_cli_command(
    ctx: typer.Context,
    json_out: bool,
    coro_factory: Callable[[PipefyClient], Awaitable[_R]],
    *,
    exit_code_2_on_value_error: bool = True,
    format_transport_query_error: Callable[[TransportQueryError], str] | None = None,
) -> None:
    """Run an async coroutine factory with a configured client and render the result.

    Args:
        ctx: Typer context (resolves settings/token from the root app).
        json_out: When True, print JSON; otherwise Rich rendering.
        coro_factory: Async callable receiving ``PipefyClient`` and returning renderable data.
        exit_code_2_on_value_error: Map ``ValueError`` to process exit code 2 (stderr).
        format_transport_query_error: Optional override for GraphQL transport errors
            (defaults to a single-line formatter).
    """
    pipefy_settings, auth = settings_and_auth_from_ctx(ctx)
    transport_fmt = format_transport_query_error or _format_transport_query_error

    async def _run() -> _R:
        client = get_authenticated_client(pipefy_settings, auth)
        return await coro_factory(client)

    try:
        data = asyncio.run(_run())
    except PipefyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    except TransportQueryError as exc:
        typer.echo(transport_fmt(exc), err=True)
        raise typer.Exit(1) from exc
    except TransportError as exc:
        typer.echo(f"Pipefy transport error: {exc}", err=True)
        raise typer.Exit(1) from exc
    except ValueError as exc:
        if exit_code_2_on_value_error:
            typer.echo(str(exc), err=True)
            raise typer.Exit(2) from exc
        raise

    if json_out:
        render_json(data)
    else:
        render_rich(data)
