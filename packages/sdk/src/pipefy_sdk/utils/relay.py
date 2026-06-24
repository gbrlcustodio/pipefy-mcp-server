from __future__ import annotations

from typing import Any


def unwrap_relay_connection_nodes(connection: Any) -> list[dict[str, Any]]:
    """Collect ``node`` dicts from a Relay-style GraphQL connection (edges → node)."""
    if not isinstance(connection, dict):
        return []
    edges = connection.get("edges")
    if not isinstance(edges, list):
        return []
    nodes: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        node = edge.get("node")
        if isinstance(node, dict):
            nodes.append(node)
    return nodes
