# Configuration

Runtime settings come from **`pipefy_mcp.settings.Settings`** ([Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)).

- **`.env`**: read from the **current working directory** (usually the repo root when you run `uv run pipefy-mcp-server` there).
- **Precedence**: values already set in the **process environment** override entries from `.env`.
- **Names and examples**: use **[`.env.example`](../.env.example)** as the single list of `PIPEFY_*` keys and placeholder values.

MCP clients (Cursor, Claude, etc.) typically pass the same keys in their `env` JSON block; that populates the process environment for the server process.
