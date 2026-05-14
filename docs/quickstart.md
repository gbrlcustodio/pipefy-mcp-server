# Quickstart

End-user install of the Pipefy MCP server in your editor or AI client. Three steps: install `uv`, create a Pipefy service account, and paste a JSON block into your MCP client. No clone required.

| Section | What it covers |
|--------|------------------|
| [Create a Pipefy service account](#create-a-pipefy-service-account) | Admin panel walkthrough, Client ID / Secret / Token URL |
| [MCP client setup](#mcp-client-setup) | Cursor, Claude Desktop, Claude Code; upgrading the pinned tag |
| [Environment variables](#environment-variables) | Required and optional `PIPEFY_*` keys |
| [How configuration is loaded](#how-configuration-is-loaded) | Pydantic Settings and process env |

> Setting up a development environment to **edit** the server? See [Contributing](contributing.md).

---

1. **Install `uv`** — drops `uv` (and `uvx`) on `PATH`:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
   For other install methods (Homebrew, winget, pipx, Windows PowerShell), see [Astral's installation guide](https://docs.astral.sh/uv/getting-started/installation/).
2. **[Create a Pipefy service account](#create-a-pipefy-service-account)** and copy the **Client ID**, **Client Secret**, and **Token endpoint URL**.
3. **[Configure your MCP client](#mcp-client-setup)** — paste the JSON block for your client, fill in the three values from step 2, restart the client, and confirm the `pipefy` server shows healthy.

On Windows, run the same flow in **PowerShell** or **Git Bash** (anywhere `uv` is on `PATH`).

---

## Create a Pipefy service account

A **service account** is a non-human Pipefy identity that issues OAuth credentials for API access. Full reference: **[Service Accounts on developers.pipefy.com](https://developers.pipefy.com/reference/service-accounts)**.

**Prerequisite:** you need an **Admin** role on your Pipefy organization.

1. Open the Pipefy **Admin Panel**.
2. Go to **Members and Permissions** → **Service Accounts**.
3. Click **[Create Service Account](https://developers.pipefy.com/reference/service-accounts)** and set the name, description, role, and expiration window (between 5 minutes and 30 days — **immutable after creation**).
4. Copy the three values Pipefy returns:
   - **Client ID** → `PIPEFY_OAUTH_CLIENT`
   - **Client Secret** → `PIPEFY_OAUTH_SECRET`
   - **Token endpoint URL** → `PIPEFY_OAUTH_URL`
5. **Add the service account to every pipe** the MCP tools should operate on. Without this, calls return permission errors even when credentials are valid.

Next, paste the three values into your MCP client config — see [MCP client setup](#mcp-client-setup) below.

---

## MCP client setup

All three clients use the same JSON shape. The `command` is `uvx`, which fetches the server from GitHub on first run and caches it locally — no clone, no `cwd`. Pin to a release tag (`@v0.1.0-beta.1` below); see [Upgrading](#upgrading) for tag bumps.

```json
"env": {
    "PIPEFY_GRAPHQL_URL": "https://app.pipefy.com/graphql",
    "PIPEFY_INTERNAL_API_URL": "https://app.pipefy.com/internal_api",
    "PIPEFY_OAUTH_URL": "https://app.pipefy.com/oauth/token",
    "PIPEFY_OAUTH_CLIENT": "<SERVICE_ACCOUNT_CLIENT_ID>",
    "PIPEFY_OAUTH_SECRET": "<SERVICE_ACCOUNT_CLIENT_SECRET>"
}
```

The three URL values are the same for every Pipefy organization on the public host — only the two `PIPEFY_OAUTH_*` secrets vary per service account.

### Cursor

1. Open **Cursor Settings → Features → MCP Servers**.
2. Click **+ Add New MCP Server**.
3. Paste the config below (replace the two `PIPEFY_OAUTH_*` placeholders).

```json
{
    "mcpServers": {
        "pipefy": {
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/gbrlcustodio/pipefy-mcp-server@v0.1.0-beta.1",
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

### Claude Desktop

MCP servers load from a JSON config file at:

| OS | File |
|----|------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

```json
{
    "mcpServers": {
        "pipefy": {
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/gbrlcustodio/pipefy-mcp-server@v0.1.0-beta.1",
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

### Claude Code

**CLI (per project)**

```bash
claude mcp add --scope project pipefy \
  -- uvx --from git+https://github.com/gbrlcustodio/pipefy-mcp-server@v0.1.0-beta.1 pipefy-mcp-server
```

Then set each env var (repeat per key):

```bash
claude mcp add-env pipefy PIPEFY_GRAPHQL_URL https://app.pipefy.com/graphql
claude mcp add-env pipefy PIPEFY_INTERNAL_API_URL https://app.pipefy.com/internal_api
claude mcp add-env pipefy PIPEFY_OAUTH_URL https://app.pipefy.com/oauth/token
claude mcp add-env pipefy PIPEFY_OAUTH_CLIENT <SERVICE_ACCOUNT_CLIENT_ID>
claude mcp add-env pipefy PIPEFY_OAUTH_SECRET <SERVICE_ACCOUNT_CLIENT_SECRET>
```

**`.mcp.json` (project root)**

```json
{
    "mcpServers": {
        "pipefy": {
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/gbrlcustodio/pipefy-mcp-server@v0.1.0-beta.1",
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

Commit `.mcp.json` with placeholders (or env injection) to share the same shape across the team without leaking secrets.

### Upgrading

To pull a newer release, change `@v0.1.0-beta.1` in `args` to the new tag and **restart your MCP client**. `uvx` caches the resolved git ref, so a fresh process is required to pick up the new revision. If a stale cache is suspected, run `uv cache clean` and restart the client again.

---

## Environment variables

Set these in the MCP client's `env:` block (see [MCP client setup](#mcp-client-setup)). The server reads them from process environment on startup.

### Required for API access

| Key | Role |
|-----|------|
| `PIPEFY_GRAPHQL_URL` | Public GraphQL endpoint. |
| `PIPEFY_INTERNAL_API_URL` | Internal GraphQL (AI automations, some relation flows). |
| `PIPEFY_OAUTH_URL` | OAuth token URL for the service account. |
| `PIPEFY_OAUTH_CLIENT` | Service account **Client ID**. |
| `PIPEFY_OAUTH_SECRET` | Service account **Client Secret**. |

The three URL values default to Pipefy's public host and are the same for every customer on the public cloud — paste them as shown above. Only the two `PIPEFY_OAUTH_*` secrets vary per service account. URLs are **validated at startup** to reject `localhost` and private hosts (SSRF guard); for development overrides, see [Contributing → Dev-only env overrides](contributing.md#dev-only-env-overrides).

### Optional

| Key | Default | Effect |
|-----|---------|--------|
| `PIPEFY_SERVICE_ACCOUNT_IDS` | _unset_ | Comma-separated Pipefy user IDs treated as service accounts. Enables [Service Account Protection](tools/members-email-webhooks.md#service-account-protection) on `remove_member_from_pipe` / `set_role`, and proactive membership checks in [`validate_ai_agent_behaviors`](tools/automations-and-ai.md#ai-agent-read--delete) for cross-pipe targets. Leave unset to skip the guards. |
| `PIPEFY_PERMISSION_DENIED_ENRICHMENT_TIMEOUT_SECONDS` | `5` | Max seconds spent enriching `PERMISSION_DENIED` errors with a membership hint. Lower to skip enrichment faster. |
| `PIPEFY_GQL_REUSE_FETCHED_GRAPHQL_SCHEMA` | `false` | Cache the introspected GraphQL schema after the first request — trades one-shot freshness for faster subsequent calls. |
| `PIPEFY_DEFAULT_WEBHOOK_NAME` | `Pipefy Webhook` | Name applied to new webhooks when the tool call omits one. |

---

## How configuration is loaded

- The server reads from **process environment** via **`pipefy_mcp.settings.Settings`** ([Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)).
- The MCP client injects its `env:` block into the spawned subprocess — that block is the only source in the `uvx` install flow. **`.env` files are not read** from the user's machine. For dev from a clone, see [Contributing](contributing.md).
- URL validation runs at startup; a startup failure means a malformed URL, while a runtime 401 means the service account credentials are wrong or the account is missing from a pipe.
