# MCP server documentation

Material in this tree describes **`pipefy-mcp-server`**: the MCP process, tool behavior, and client wiring.

## Contents

| Path | Description |
|------|-------------|
| [`tools/`](tools/cross-cutting.md) | Per-domain MCP tool reference (parameters, edge cases, cross-cutting behavior) |

Start with [`tools/cross-cutting.md`](tools/cross-cutting.md) for pagination, IDs, `debug`, permissions, and error shape — then open the domain guide you need.

For install, environment variables, and Cursor / Claude client JSON, use the shared guide **[`../setup.md`](../setup.md)** (see [MCP client setup](../setup.md#mcp-client-setup)).

The MCP ↔ CLI coverage matrix lives at **[`../parity.md`](../parity.md)**.
