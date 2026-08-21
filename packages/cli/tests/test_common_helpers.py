"""Unit tests for shared CLI helpers in ``pipefy_cli.commands._common``."""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer

from pipefy_cli.commands._common import (
    export_poll_max_rounds,
    poll_export_until_done,
    write_export_csv_to_stdout,
)


@pytest.mark.asyncio
async def test_poll_export_until_done_returns_fileurl_when_done():
    fetch = AsyncMock(return_value={"node": {"state": "done", "fileURL": "https://x"}})

    url = await poll_export_until_done(
        fetch,
        "exp-1",
        lambda raw: raw.get("node") or {},
        max_rounds=3,
        delay_seconds=0.0,
    )

    assert url == "https://x"
    fetch.assert_awaited_once_with("exp-1")


@pytest.mark.asyncio
async def test_poll_export_until_done_reads_only_declared_fileurl():
    """Report export types declare ``fileURL``; a ``fileUrl``-only node has no url."""
    fetch = AsyncMock(return_value={"node": {"state": "done", "fileUrl": "https://y"}})

    with pytest.raises(ValueError, match="fileURL is missing"):
        await poll_export_until_done(
            fetch,
            "exp-2",
            lambda raw: raw.get("node") or {},
            max_rounds=3,
            delay_seconds=0.0,
        )


@pytest.mark.asyncio
async def test_poll_export_until_done_raises_on_failed_state():
    fetch = AsyncMock(return_value={"node": {"state": "failed"}})

    with pytest.raises(ValueError, match="Export failed"):
        await poll_export_until_done(
            fetch,
            "exp-3",
            lambda raw: raw.get("node") or {},
            max_rounds=3,
            delay_seconds=0.0,
        )


@pytest.mark.asyncio
async def test_poll_export_until_done_raises_when_done_without_url():
    fetch = AsyncMock(return_value={"node": {"state": "done"}})

    with pytest.raises(ValueError, match="fileURL is missing"):
        await poll_export_until_done(
            fetch,
            "exp-4",
            lambda raw: raw.get("node") or {},
            max_rounds=3,
            delay_seconds=0.0,
        )


@pytest.mark.asyncio
async def test_poll_export_until_done_times_out_after_max_rounds():
    fetch = AsyncMock(return_value={"node": {"state": "processing"}})

    with pytest.raises(ValueError, match="Timed out"):
        await poll_export_until_done(
            fetch,
            "exp-5",
            lambda raw: raw.get("node") or {},
            max_rounds=2,
            delay_seconds=0.0,
        )

    assert fetch.await_count == 2


def test_export_poll_max_rounds_maps_seconds_to_rounds():
    assert export_poll_max_rounds(2.0) == 1
    assert export_poll_max_rounds(2.0, delay_seconds=2.0) == 1
    assert export_poll_max_rounds(5.0, delay_seconds=2.0) == 3
    assert export_poll_max_rounds(90.0) == 45


def test_export_poll_max_rounds_rejects_non_positive_budget():
    with pytest.raises(ValueError):
        export_poll_max_rounds(0.0)
    with pytest.raises(ValueError):
        export_poll_max_rounds(-1.0)


@pytest.mark.asyncio
async def test_write_export_csv_to_stdout_streams_chunks(capsysbinary):
    fetch = AsyncMock(
        return_value={"node": {"state": "done", "fileURL": "https://example/csv"}}
    )

    async def fake_stream(url: str, *, max_bytes: int) -> AsyncIterator[bytes]:
        assert url == "https://example/csv"
        assert max_bytes == 32
        for piece in (b"alpha,", b"beta,", b"gamma\n"):
            yield piece

    with patch("pipefy_cli.commands._common.stream_bytes", new=fake_stream):
        await write_export_csv_to_stdout(
            export_id="exp-9",
            poll_fetch=fetch,
            unwrap_status=lambda raw: raw.get("node") or {},
            poll_timeout_seconds=2.0,
            max_bytes=32,
        )

    sys.stdout.buffer.flush()
    captured = capsysbinary.readouterr()
    assert captured.out == b"alpha,beta,gamma\n"


@pytest.mark.asyncio
async def test_write_export_csv_to_stdout_propagates_poll_failure():
    fetch = AsyncMock(return_value={"node": {"state": "failed"}})

    async def never_called(url: str, *, max_bytes: int) -> AsyncIterator[bytes]:
        raise AssertionError("stream_bytes should not run after a failed poll")
        yield b""  # pragma: no cover

    with patch("pipefy_cli.commands._common.stream_bytes", new=never_called):
        with pytest.raises(ValueError, match="Export failed"):
            await write_export_csv_to_stdout(
                export_id="exp-10",
                poll_fetch=fetch,
                unwrap_status=lambda raw: raw.get("node") or {},
                poll_timeout_seconds=2.0,
            )


def test_run_pipefy_client_coroutine_runs_factory_and_returns(monkeypatch):
    """``run_pipefy_client_coroutine`` resolves the configured client and awaits the factory."""
    from unittest.mock import MagicMock

    from pipefy_cli.commands import _common
    from pipefy_cli.commands._common import run_pipefy_client_coroutine

    captured: dict[str, Any] = {}

    def fake_get_client(settings: object, auth: object) -> object:
        captured["settings"] = settings
        bearer = auth.bearer_token  # type: ignore[attr-defined]
        captured["bearer_token"] = bearer.value if bearer is not None else None
        return "client-instance"

    async def factory(client: object) -> str:
        captured["received_client"] = client
        return "done"

    sentinel_settings = object()
    sentinel_auth = _common.AuthContext(
        bearer_token=_common.BearerToken(value="abc", source="flag"),
        service_account=None,
        oidc_client=None,
    )
    monkeypatch.setattr(_common, "get_authenticated_client", fake_get_client)
    monkeypatch.setattr(
        _common,
        "settings_and_auth_from_ctx",
        lambda ctx: (sentinel_settings, sentinel_auth),
    )

    result = run_pipefy_client_coroutine(MagicMock(), factory)

    assert result == "done"
    assert captured == {
        "settings": sentinel_settings,
        "bearer_token": "abc",
        "received_client": "client-instance",
    }


def test_run_pipefy_client_coroutine_maps_pipefy_error_to_exit_1(monkeypatch):
    """``PipefyError`` raised by the factory exits with code 1."""
    from unittest.mock import MagicMock

    import typer
    from pipefy_sdk.exceptions import PipefyError

    from pipefy_cli.commands import _common
    from pipefy_cli.commands._common import run_pipefy_client_coroutine

    monkeypatch.setattr(
        _common, "get_authenticated_client", lambda settings, auth: object()
    )
    monkeypatch.setattr(
        _common,
        "settings_and_auth_from_ctx",
        lambda ctx: (
            object(),
            _common.AuthContext(
                bearer_token=None, service_account=None, oidc_client=None
            ),
        ),
    )

    async def factory(client: object) -> str:
        raise PipefyError("graphql denied")

    with pytest.raises(typer.Exit) as excinfo:
        run_pipefy_client_coroutine(MagicMock(), factory)

    assert excinfo.value.exit_code == 1


def test_run_pipefy_client_coroutine_graphql_error_keeps_the_code_suffix(
    monkeypatch, capsys
):
    """The GraphQL branch has to stay above ``PipefyError`` or the code suffix is lost.

    ``PipefyGraphQLError`` is a ``PipefyError``, so swapping the two catches sends
    it to the generic branch, which echoes ``str(exc)`` and never runs the
    formatter. ``run_cli_command`` has the portal detach test for this; the
    coroutine runner had nothing.
    """
    from pipefy_sdk import PipefyGraphQLError

    from pipefy_cli.commands import _common
    from pipefy_cli.commands._common import run_pipefy_client_coroutine

    monkeypatch.setattr(
        _common, "get_authenticated_client", lambda settings, auth: object()
    )
    monkeypatch.setattr(
        _common,
        "settings_and_auth_from_ctx",
        lambda ctx: (
            object(),
            _common.AuthContext(
                bearer_token=None, service_account=None, oidc_client=None
            ),
        ),
    )

    async def factory(client: object) -> None:
        raise PipefyGraphQLError(
            [
                {
                    "message": "Couldn't find PortalInterface with",
                    "extensions": {"code": "RECORD_NOT_FOUND"},
                }
            ]
        )

    with pytest.raises(typer.Exit) as excinfo:
        run_pipefy_client_coroutine(MagicMock(), factory)

    assert excinfo.value.exit_code == 1
    assert (
        capsys.readouterr().err.strip()
        == "Couldn't find PortalInterface with (RECORD_NOT_FOUND)"
    )


def test_run_pipefy_client_coroutine_maps_value_error_when_configured(monkeypatch):
    """Optional ``value_error_exit_code`` maps export failures to stderr + exit."""
    from pipefy_cli.commands import _common
    from pipefy_cli.commands._common import run_pipefy_client_coroutine

    monkeypatch.setattr(
        _common, "get_authenticated_client", lambda settings, auth: object()
    )
    monkeypatch.setattr(
        _common,
        "settings_and_auth_from_ctx",
        lambda ctx: (
            object(),
            _common.AuthContext(
                bearer_token=None, service_account=None, oidc_client=None
            ),
        ),
    )

    async def factory(client: object) -> None:
        raise ValueError("Export failed (state='failed').")

    with pytest.raises(typer.Exit) as excinfo:
        run_pipefy_client_coroutine(MagicMock(), factory, value_error_exit_code=1)

    assert excinfo.value.exit_code == 1


def test_run_pipefy_client_coroutine_broken_pipe_exits_0(monkeypatch):
    """``BrokenPipeError`` (e.g. ``| head``) exits 0 without a traceback."""
    from pipefy_cli.commands import _common
    from pipefy_cli.commands._common import run_pipefy_client_coroutine

    monkeypatch.setattr(
        _common, "get_authenticated_client", lambda settings, auth: object()
    )
    monkeypatch.setattr(
        _common,
        "settings_and_auth_from_ctx",
        lambda ctx: (
            object(),
            _common.AuthContext(
                bearer_token=None, service_account=None, oidc_client=None
            ),
        ),
    )

    async def factory(client: object) -> None:
        raise BrokenPipeError()

    with pytest.raises(typer.Exit) as excinfo:
        run_pipefy_client_coroutine(MagicMock(), factory, value_error_exit_code=1)

    assert excinfo.value.exit_code == 0
