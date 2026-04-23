# Setup

Single entry point for **first-time install**, **environment variables**, and **MCP client** wiring. Prerequisites: a [Pipefy Service Account](https://app.pipefy.com/) (Admin → Service Accounts), and add that account to every pipe the tools should use.

| Section | What it covers |
|--------|------------------|
| [Quick start](#quick-start) | Clone, `uv`, `.env`, smoke test, unit tests |
| [How configuration is loaded](#how-configuration-is-loaded) | Pydantic Settings, CWD, precedence |
| [Environment variables](#environment-variables) | Required vs optional `PIPEFY_*` keys |
| [MCP client setup](#mcp-client-setup) | Cursor, Claude Desktop, Claude Code |
| [Bootstrap script](#optional-bootstrap-script) | One-shot `uv sync` + `.env` template |

---

## Quick start

1. **Install [uv](https://docs.astral.sh/uv/getting-started/installation/)** (it manages Python 3.11+ for this project).

2. **Clone and install dependencies**
   ```bash
   git clone https://github.com/gbrlcustodio/pipefy-mcp-server.git
   cd pipefy-mcp-server
   uv sync
   ```

3. **Environment file** — from the repo root:
   ```bash
   cp .env.example .env
   ```
   Edit **`.env`** and set at least the OAuth client and secret from your service account. Canonical names and placeholders: **[`../.env.example`](../.env.example)**.

4. **Smoke test (optional)** — confirms the process starts (stop with Ctrl+C when satisfied):
   ```bash
   uv run pipefy-mcp-server
   ```

5. **Tests without calling Pipefy (optional)** — no `PIPEFY_*` credentials required:
   ```bash
   uv run pytest -m "not integration"
   ```

6. **Register the server in your IDE** — [MCP client setup](#mcp-client-setup) below. Prefer pointing the client’s `cwd` at this repo and keeping secrets in **`.env`** so you do not duplicate them in JSON.

On Windows, use the same commands in **PowerShell** or **Git Bash** (where `uv` is on `PATH`).

---

## How configuration is loaded

Runtime settings come from **`pipefy_mcp.settings.Settings`** ([Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)).

- **`.env`**: read from the **current working directory** (usually the repo root when you run `uv run pipefy-mcp-server` from there, or when the MCP client sets `cwd` to the clone).
- **Precedence**: values already in the **process environment** (including the MCP client `env` block) **override** entries from `.env`.
- **Same keys everywhere** — use the names from **[`.env.example`](../.env.example)** in `.env` or in the client JSON; the server does not care which source won, as long as the process sees the variables.

---

## Environment variables

### Required for API access

| Key | Role |
|-----|------|
| `PIPEFY_GRAPHQL_URL` | Public GraphQL endpoint (default in `.env.example`). |
| `PIPEFY_INTERNAL_API_URL` | Internal GraphQL (AI automations, some relation flows). Use the value from [`.env.example`](../.env.example). |
| `PIPEFY_OAUTH_URL` | OAuth token URL for the service account. |
| `PIPEFY_OAUTH_CLIENT` | Service account client ID. |
| `PIPEFY_OAUTH_SECRET` | Service account client secret. |

`PIPEFY_INTERNAL_API_URL` points at Pipefy’s internal GraphQL; it is required for tools that use that path (e.g. AI automations, some relations). Values are **validated at startup** — public Pipefy hosts are the normal case; `localhost` / private hosts are rejected to avoid SSRF unless you use the insecure-dev flags in [`.env.example`](../.env.example).

### Optional

| Key | Default | Effect |
|-----|---------|--------|
| `PIPEFY_SERVICE_ACCOUNT_IDS` | _unset_ | Comma-separated Pipefy user IDs treated as service accounts. Enables [Service Account Protection](tools/members-email-webhooks.md#service-account-protection) on `remove_member_from_pipe` / `set_role`, and proactive membership checks in [`validate_ai_agent_behaviors`](tools/automations-and-ai.md#ai-agent-read--delete) for cross-pipe targets. Leave unset to skip the guards. |

All other optional flags (insecure dev URLs, webhooks, introspection cache, etc.) are documented in **[`.env.example`](../.env.example)** only.

---

## MCP client setup

**Recommended:** set the client’s working directory to your **clone root** and use **`.env`** for `PIPEFY_*` values. Then the JSON `env` block can be minimal or empty for local dev. If you put secrets only in JSON, use the same keys as [`.env.example`](../.env.example).

Use this **`env` shape** when you need to inline values (e.g. CI or machines without a `.env` file). Include **`PIPEFY_INTERNAL_API_URL`** for parity with full tool coverage (same as [`.env.example`](../.env.example)).

```json
"env": {
    "PIPEFY_GRAPHQL_URL": "https://app.pipefy.com/graphql",
    "PIPEFY_INTERNAL_API_URL": "https://app.pipefy.com/internal_api",
    "PIPEFY_OAUTH_URL": "https://app.pipefy.com/oauth/token",
    "PIPEFY_OAUTH_CLIENT": "<SERVICE_ACCOUNT_CLIENT_ID>",
    "PIPEFY_OAUTH_SECRET": "<SERVICE_ACCOUNT_CLIENT_SECRET>"
}
```

### Cursor

1. Open **Cursor Settings → Features → MCP Servers**.
2. Click **+ Add New MCP Server**.
3. Use a config like the one below (replace the path and placeholders).

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
                "PIPEFY_INTERNAL_API_URL": "https://app.pipefy.com/internal_api",
                "PIPEFY_OAUTH_URL": "https://app.pipefy.com/oauth/token",
                "PIPEFY_OAUTH_CLIENT": "<SERVICE_ACCOUNT_CLIENT_ID>",
                "PIPEFY_OAUTH_SECRET": "<SERVICE_ACCOUNT_CLIENT_SECRET>"
            }
        }
    }
}
```

Set `cwd` to your clone root so the server can read **`.env`** there; you may omit keys from `env` that are already set in `.env`.

### Claude Desktop

MCP servers load from a JSON config file. You can keep credentials in **`.env`** at the repo root (see [How configuration is loaded](#how-configuration-is-loaded)) and use a minimal `env` in JSON if `cwd` points at the clone.

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

### Claude Code

Either rely on [`.env.example`](../.env.example) → **`.env`** at the repo root, or set vars with `claude mcp add-env`.

**CLI (per project)**

```bash
claude mcp add --scope project pipefy \
  -- uv run --directory /absolute/path/to/pipefy-mcp-server pipefy-mcp-server
```

Then (repeat for each key you need, matching [`.env.example`](../.env.example)):

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

The CLI flow is quick for local tests. Committing **`.mcp.json`** without secrets (placeholders or env injection) can help teams share the same shape.

---

## Optional bootstrap script

From the **repository root**, after installing `uv`, you can run:

`./bootstrap.sh`

Purpose:

- Run **`uv sync`**
- If **`.env`** is missing, copy **`.env.example`** → **`.env`** (does not overwrite an existing `.env`)

On Windows, run the [Quick start](#quick-start) steps manually if you do not use Git Bash.
