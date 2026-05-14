"""Shared Typer helpers for domain command modules."""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import typer
from pipefy_sdk import PipefyClient, PipefySettings
from pipefy_sdk.exceptions import PipefyError

from pipefy_cli.auth import get_authenticated_client
from pipefy_cli.output import render_json, render_rich

_T = TypeVar("_T")


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


def run_pipefy_client_coroutine(
    ctx: typer.Context,
    coro_factory: Callable[[PipefyClient], Awaitable[_T]],
) -> _T:
    """Run ``asyncio.run`` on a coroutine built with a configured :class:`PipefyClient`.

    Args:
        ctx: Typer context (resolves settings/token from the root app).
        coro_factory: Async callable receiving an authenticated client.

    Returns:
        The coroutine result.

    Raises:
        typer.Exit: On :class:`PipefyError` (exit code 1).
    """
    pipefy_settings, token = settings_and_token(ctx)

    async def _run() -> _T:
        client = get_authenticated_client(pipefy_settings, bearer_token=token)
        return await coro_factory(client)

    try:
        return asyncio.run(_run())
    except PipefyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


def settings_and_token(ctx: typer.Context) -> tuple[PipefySettings, str | None]:
    """Resolve root CLI context object into settings and optional bearer token."""
    root = ctx.find_root()
    obj = root.obj
    return obj["pipefy_settings"], obj.get("token")


def authenticated_client_from_ctx(ctx: typer.Context) -> PipefyClient:
    """Build a :class:`PipefyClient` using the same auth path as ``run_cli_command``."""
    pipefy_settings, token = settings_and_token(ctx)
    return get_authenticated_client(pipefy_settings, bearer_token=token)


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
    coro_factory: Callable[[PipefyClient], Awaitable[Any]],
    *,
    exit_code_2_on_value_error: bool = False,
) -> None:
    """Run an async coroutine factory with a configured client and render the result.

    Args:
        ctx: Typer context (resolves settings/token from the root app).
        json_out: When True, print JSON; otherwise Rich rendering.
        coro_factory: Async callable receiving ``PipefyClient``.
        exit_code_2_on_value_error: Map ``ValueError`` to process exit code 2 (stderr).
    """
    pipefy_settings, token = settings_and_token(ctx)

    async def _run() -> Any:
        client = get_authenticated_client(pipefy_settings, bearer_token=token)
        return await coro_factory(client)

    try:
        data = asyncio.run(_run())
    except PipefyError as exc:
        typer.echo(str(exc), err=True)
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
