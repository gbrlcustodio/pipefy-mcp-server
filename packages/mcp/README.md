# pipefy-mcp-server

MCP server package for Pipefy. See the [repository README](../../README.md) for installation, configuration, and tool documentation.

## Development

From the **repository root**, run `uv sync --all-packages --dev` (or `uv sync`) so workspace members (`pipefy-ai-sdk`, this package) resolve correctly. Then run tests with `uv run pytest packages/mcp/tests` from the root, or `cd packages/mcp && uv run pytest tests/` after sync—the MCP package’s pytest config adds `packages/sdk/tests` on `pythonpath` so `_shared` live-credential helpers resolve without installing a separate test bundle.
