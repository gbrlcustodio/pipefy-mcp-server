# MCP client setup

Register **pipefy-mcp-server** in Cursor, Claude Desktop, or Claude Code. Use a **Service Account** from Pipefy Admin; add that account to pipes the tools should access.

Use the same **`PIPEFY_*` keys** as in [`.env.example`](../.env.example). For precedence (`.env` vs process env) and Pydantic loading, see **[Configuration](configuration.md)**.

---

## Cursor

1. Open **Cursor Settings → Features → MCP Servers**.
2. Click **+ Add New MCP Server**.
3. Use a config like the one below (replace paths and placeholders).

```json
{
    "mcpServers": {
        "pipefy": {
            "cwd": "/absolute/path/to/pipefy-mcp-server",
            "command": "uv",
            "args": [
                "run",
                "--directory",
                ".",
                "pipefy-mcp-server"
            ],
            "env": {
                "PIPEFY_GRAPHQL_URL": "https://app.pipefy.com/graphql",
                "PIPEFY_OAUTH_URL": "https://app.pipefy.com/oauth/token",
                "PIPEFY_OAUTH_CLIENT": "<SERVICE_ACCOUNT_CLIENT_ID>",
                "PIPEFY_OAUTH_SECRET": "<SERVICE_ACCOUNT_CLIENT_SECRET>"
            }
        }
    }
}
```

Set `cwd` to your clone root so the server resolves `.env` there when present.

---

## Claude Desktop

MCP servers are loaded from a JSON config file. Optionally copy [`.env.example`](../.env.example) to `.env` at the repo root and fill credentials (same names as in the `env` block below).

**Config paths**

| OS | File |
|----|------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

```json
{
    "mcpServers": {
        "pipefy": {
            "command": "uv",
            "args": [
                "run",
                "--directory",
                "/absolute/path/to/pipefy-mcp-server",
                "pipefy-mcp-server"
            ],
            "env": {
                "PIPEFY_GRAPHQL_URL": "https://app.pipefy.com/graphql",
                "PIPEFY_INTERNAL_API_URL": "https://app.pipefy.com/internal_api",
                "PIPEFY_OAUTH_URL": "https://app.pipefy.com/oauth/token",
                "PIPEFY_OAUTH_CLIENT": "<SERVICE_ACCOUNT_CLIENT_ID>",
                "PIPEFY_OAUTH_SECRET": "<SERVICE_ACCOUNT_CLIENT_SECRET>"
            }
        }
    }
}
```

Replace `/absolute/path/to/pipefy-mcp-server` with your clone path.

---

## Claude Code

Either rely on [`.env.example`](../.env.example) → `.env` at the repo root, or set vars with `claude mcp add-env`.

**CLI (per project)**

```bash
claude mcp add --scope project pipefy \
  -- uv run --directory /absolute/path/to/pipefy-mcp-server pipefy-mcp-server
```

Then (repeat for each key from [`.env.example`](../.env.example)):

```bash
claude mcp add-env pipefy PIPEFY_OAUTH_CLIENT <YOUR_CLIENT_ID>
claude mcp add-env pipefy PIPEFY_OAUTH_SECRET <YOUR_CLIENT_SECRET>
claude mcp add-env pipefy PIPEFY_GRAPHQL_URL https://app.pipefy.com/graphql
claude mcp add-env pipefy PIPEFY_INTERNAL_API_URL https://app.pipefy.com/internal_api
claude mcp add-env pipefy PIPEFY_OAUTH_URL https://app.pipefy.com/oauth/token
```

**`.mcp.json` (project root)**

```json
{
    "mcpServers": {
        "pipefy": {
            "command": "uv",
            "args": [
                "run",
                "--directory",
                "/absolute/path/to/pipefy-mcp-server",
                "pipefy-mcp-server"
            ],
            "env": {
                "PIPEFY_GRAPHQL_URL": "https://app.pipefy.com/graphql",
                "PIPEFY_INTERNAL_API_URL": "https://app.pipefy.com/internal_api",
                "PIPEFY_OAUTH_URL": "https://app.pipefy.com/oauth/token",
                "PIPEFY_OAUTH_CLIENT": "<SERVICE_ACCOUNT_CLIENT_ID>",
                "PIPEFY_OAUTH_SECRET": "<SERVICE_ACCOUNT_CLIENT_SECRET>"
            }
        }
    }
}
```

The CLI flow is quick for local tests; committing `.mcp.json` (without secrets) helps teams share the same shape—inject secrets via environment or `add-env`.
