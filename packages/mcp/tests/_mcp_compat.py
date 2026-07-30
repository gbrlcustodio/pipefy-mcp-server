"""In-memory server/client harness for the tool tests.

``mcp`` 2.0 removed ``mcp.shared.memory.create_connected_server_and_client_session``
in favour of ``mcp.client.Client``, which takes an ``MCPServer`` directly and owns
the in-memory transport and the handshake. Every tool test drives a server through
this one function, so the swap lives here rather than in the 29 test modules that
call it.

Kept as a function with the old name and signature so a test reads the same before
and after: ``async with create_connected_server_and_client_session(server) as
session``. The object yielded is a ``Client``, not a ``ClientSession``. For the two
methods the suite uses (``call_tool`` and ``list_tools``) the call shape is
identical; a test that reaches for a paginated ``list_*`` needs ``cursor=`` rather
than ``params=PaginatedRequestParams(...)``.

``mode="legacy"`` is the deliberate default. ``Client`` otherwise negotiates
2026-07-28, where the server cannot call the client, and elicitation tests
(``pipe_config``, ``service_account``) drive exactly that back channel. Legacy also
matches what this server negotiates in production today, so the suite exercises the
protocol revision the deployment actually serves. Adopting 2026-07-28 is a separate
piece of work from the SDK upgrade (see #543); when it happens, the override below
is the one place to flip.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from mcp.client import Client

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

__all__ = ["create_connected_server_and_client_session"]


@asynccontextmanager
async def create_connected_server_and_client_session(
    server: MCPServer, **kwargs: Any
) -> AsyncIterator[Client]:
    """Connect an in-memory client to ``server`` and yield it for the block.

    Accepts the same keyword arguments the removed helper did (``raise_exceptions``,
    ``elicitation_callback``, ``read_timeout_seconds``, the callbacks), passing them
    straight through to ``Client``.

    ``read_timeout_seconds`` is coerced from ``timedelta`` to the plain float of
    seconds 2.0 expects. Absorbing it here keeps the 44 call sites that pass a
    ``timedelta`` readable as timeouts; without the coercion they fail inside anyio
    with ``unsupported operand type(s) for +: 'float' and 'datetime.timedelta'``,
    which points nowhere near the call.
    """
    timeout = kwargs.get("read_timeout_seconds")
    if isinstance(timeout, timedelta):
        kwargs["read_timeout_seconds"] = timeout.total_seconds()
    kwargs.setdefault("mode", "legacy")
    async with Client(server, **kwargs) as client:
        yield client
