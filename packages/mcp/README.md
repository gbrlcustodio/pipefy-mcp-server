# pipefy-mcp-server

MCP server for Pipefy — **128 tools** for AI agents (Cursor, Claude Desktop, Claude Code, and any MCP-compatible client). Depends on [`pipefy-sdk`](../sdk/README.md) for all GraphQL and API logic.

## Install (pre-launch, v0.1 → v0.5)

```sh
uvx --from git+https://github.com/<owner>/pipefy-labs --refresh pipefy-mcp-server
```

> At v1.0 this moves to `uvx pipefy-mcp-server` from PyPI.

## Configuration

Set the following environment variables (or add to a `.env` file in your working directory):

```env
PIPEFY_SERVICE_ACCOUNT_CLIENT_ID=your_client_id
PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET=your_client_secret
# Non-prod environments only:
# PIPEFY_BASE_URL=https://<your-api-host>
# PIPEFY_AUTH_URL=https://<your-signin-host>/realms/<realm>
```

`PIPEFY_BASE_URL` defaults to `https://app.pipefy.com` (drives the four API endpoints) and `PIPEFY_AUTH_URL` defaults to `https://signin.pipefy.com/realms/pipefy` (the OIDC issuer). Set them only for non-prod environments.

Full guide: [`docs/setup.md`](../../docs/setup.md).

## MCP client setup (Cursor, Claude Desktop)

Step-by-step JSON samples live in [`docs/setup.md#mcp-client-setup`](../../docs/setup.md#mcp-client-setup).

## Tools

128 tools across nine domains — see the root [`README.md`](../../README.md#mcp-tools) for the full table with per-area links. Deep reference: [`docs/mcp/tools/`](../../docs/mcp/tools/cross-cutting.md) (start with [`cross-cutting.md`](../../docs/mcp/tools/cross-cutting.md)).

## Development

From the **repository root**:

```bash
uv sync
uv run pytest packages/mcp/tests     # MCP tests in isolation
uv run ruff check packages/mcp/src   # lint
```

See the root [`README.md`](../../README.md) and [`AGENTS.md`](../../AGENTS.md) for contributor guidance.
