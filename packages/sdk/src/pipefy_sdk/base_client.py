"""Transitional shim: the executor moved to ``pipefy_sdk.graphql_executor``.

``BasePipefyClient`` is retained as an alias while services migrate from
inheriting the executor to receiving an injected :class:`GraphQLExecutor`.
Removed once every service is converted.
"""

from __future__ import annotations

from pipefy_sdk.graphql_executor import (
    HttpxGraphQLExecutor as BasePipefyClient,
)
from pipefy_sdk.utils.relay import unwrap_relay_connection_nodes

__all__ = ["BasePipefyClient", "unwrap_relay_connection_nodes"]
