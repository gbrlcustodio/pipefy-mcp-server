# MCP server documentation

Material in this tree describes **`pipefy-mcp-server`**: the MCP process, tool behavior, and client wiring.

## Contents

| Path | Description |
|------|-------------|
| [`tools/`](tools/cross-cutting.md) | Per-domain MCP tool reference (parameters, edge cases, cross-cutting behavior) |

Start with [`tools/cross-cutting.md`](tools/cross-cutting.md) for pagination, IDs, `debug`, permissions, and error shape — then open the domain guide you need.

For install and per-client MCP wiring (Cursor, Claude Desktop, Claude Code, Codex), see the root [`README.md#installation`](../../README.md#installation). For environment variables and `config.toml`, see [`../config.md`](../config.md). Edge cases (`errSecParam`, `.mcp.json`, local-clone alternative): [`packages/mcp/README.md`](../../packages/mcp/README.md).

The MCP ↔ CLI coverage matrix lives at **[`../parity.md`](../parity.md)**.
