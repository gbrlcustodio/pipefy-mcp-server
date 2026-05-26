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

### URL configuration

| Key | Default | Effect |
|-----|---------|--------|
| `PIPEFY_BASE_URL` | `https://app.pipefy.com` | Pipefy API host root. Drives `graphql_url`, `internal_api_url`, `interfaces_graphql_url`, and the service-account OAuth token endpoint (all four are computed properties). Set to a different host for non-prod environments, regional / proxy deployments, or local development (with `PIPEFY_ALLOW_INSECURE_URLS`). |
| `PIPEFY_AUTH_URL` | `https://signin.pipefy.com/realms/pipefy` | Full OIDC issuer URL for the stored-session tier. Set to the full issuer URL for non-prod IdPs. |
| `PIPEFY_SERVICE_ACCOUNT_CLIENT_ID` | _unset_ | Service-account client_id (OAuth 2.0 RFC 6749). |
| `PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET` | _unset_ | Service-account client_secret. |
| `PIPEFY_TOKEN` | _unset_ | Pre-issued bearer for the static-token tier; outranks the service-account triple and any stored session. |
| `PIPEFY_AUTH_CLIENT_ID` | `pipefy-cli` | OIDC public client id registered at the issuer (rarely overridden). |

An operator on prod typically sets just the credentials (`PIPEFY_SERVICE_ACCOUNT_CLIENT_ID` + `PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET`, or `PIPEFY_TOKEN`). Non-prod operators add `PIPEFY_BASE_URL` and `PIPEFY_AUTH_URL`.

Values are **validated at startup** with per-field regex patterns (`https?://` for URL fields, numeric for `PIPEFY_ORG_ID`, non-whitespace for credentials). `localhost` / private hosts are rejected to avoid SSRF unless you use the insecure-dev flags in [`.env.example`](../.env.example). **Empty / malformed values raise.** Any `PIPEFY_*` env var that does not match its pattern is rejected at construction — unset the variable to fall back to the default.

> **Legacy names:** `PIPEFY_OAUTH_CLIENT` and `PIPEFY_OAUTH_SECRET` are still honored (with a one-shot stderr deprecation warning) for back-compat. They will be removed in a future beta. The `PIPEFY_OAUTH_URL` alias was dropped — the OAuth token endpoint now derives from `PIPEFY_BASE_URL`. See [docs/MIGRATION.md](MIGRATION.md#service-account-env-var-rename).

### Optional

| Key | Default | Effect |
|-----|---------|--------|
| `PIPEFY_ORG_ID` | _unset_ | Default **numeric organization id** for `pipefy org get` when you omit the positional argument (same id as in `pipefy pipe list --json` under `organizations[].id`). Optional convenience only; not required for MCP or most CLI commands. |
| `PIPEFY_SERVICE_ACCOUNT_IDS` | _unset_ | Comma-separated Pipefy user IDs treated as service accounts. Enables [Service Account Protection](mcp/tools/members-email-webhooks.md#service-account-protection) on `remove_member_from_pipe` / `set_role`, and proactive membership checks in [`validate_ai_agent_behaviors`](mcp/tools/automations-and-ai.md#ai-agent-read--delete) for cross-pipe targets. Leave unset to skip the guards. |

All other optional flags (insecure dev URLs, webhooks, introspection cache, etc.) are documented in **[`.env.example`](../.env.example)** only.

> **CLI users:** the variables above feed the **service-account** path. The `pipefy` CLI also supports an interactive `pipefy auth login` flow (browser-based, per-user) and a direct `PIPEFY_TOKEN` bearer. The four-tier precedence between them is documented in **[`cli/auth.md`](cli/auth.md)**.

---

## MCP client setup

**Recommended:** set the client’s working directory to your **clone root** and use **`.env`** for `PIPEFY_*` values. Then the JSON `env` block can be minimal or empty for local dev. If you put secrets only in JSON, use the same keys as [`.env.example`](../.env.example).

Use this **`env` shape** when you need to inline values (e.g. CI or machines without a `.env` file). On prod, only the service-account triple is required. Non-prod operators add `PIPEFY_BASE_URL` (and `PIPEFY_AUTH_URL` when the OIDC issuer differs):

```json
"env": {
    "PIPEFY_SERVICE_ACCOUNT_CLIENT_ID": "<SERVICE_ACCOUNT_CLIENT_ID>",
    "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET": "<SERVICE_ACCOUNT_CLIENT_SECRET>"
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
                "PIPEFY_SERVICE_ACCOUNT_CLIENT_ID": "<SERVICE_ACCOUNT_CLIENT_ID>",
                "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET": "<SERVICE_ACCOUNT_CLIENT_SECRET>"
            }
        }
    }
}
```

Set `cwd` to your clone root so the server can read **`.env`** there; you may omit keys from `env` that are already set in `.env`. Non-prod operators add `"PIPEFY_BASE_URL": "https://<api-host>"` (and `PIPEFY_AUTH_URL` if the OIDC issuer differs).

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
                "PIPEFY_SERVICE_ACCOUNT_CLIENT_ID": "<SERVICE_ACCOUNT_CLIENT_ID>",
                "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET": "<SERVICE_ACCOUNT_CLIENT_SECRET>"
            }
        }
    }
}
```

Replace `/absolute/path/to/pipefy-mcp-server` with your clone path.

### Claude Code

Either rely on [`.env.example`](../.env.example) → **`.env`** at the repo root, or set vars with `claude mcp add-env`.

**Plugin install (recommended)**

The repo ships a Claude Code plugin that registers the MCP server, a `/pipefy:install` slash command, and a `/pipefy:login` slash command:

```text
/plugin marketplace add gbrlcustodio/pipefy-mcp-server
/plugin install pipefy
/pipefy:install
/pipefy:login
```

`/pipefy:install` is a one-shot that runs `uv tool install` to put a stable `pipefy` binary on PATH (idempotent; rerunning when `pipefy` is already on PATH surfaces `pipefy --version` and stops). `/pipefy:login` runs the OAuth browser flow and stores the session in the OS keychain; it requires `pipefy` on PATH and will tell you to run `/pipefy:install` first if it isn't. Subsequent `pipefy auth status` / `pipefy auth logout` invocations use the same binary `/pipefy:install` put in place. A live MCP server picks up the rotated session on its next tool call; if the server failed to start because credentials were missing, restart it (or restart Claude Code) after login completes. Terminal-based users can run `pipefy auth login` directly instead.

On macOS, `pipefy auth login` may exit with `errSecParam (-25244)` at the final keychain-write step even though OAuth itself succeeded. The cause is not yet reliably diagnosed — direct `keyring.set_password` calls from the same uv-tool-installed Python succeed under repro testing, so this is likely a transient `Security.framework` condition rather than a deterministic per-binary ACL problem. If it occurs, retry the slash command first; as a fallback, run `pipefy auth login` once from a regular Terminal.app session and approve any macOS keychain dialog that appears. Issue #235 tracks platform-aware error messaging.

Configure the plugin-spawned MCP server's environment by editing the `env` block of the `pipefy` MCP server entry in your Claude Code settings (`~/.claude.json` or via the settings UI; the plugin's `.mcp.json` ships `command`+`args` only). Prod operators set only the service-account triple (`PIPEFY_BASE_URL` and `PIPEFY_AUTH_URL` default to Pipefy production); non-prod operators add either or both:

```json
{
  "mcpServers": {
    "pipefy": {
      "env": {
        "PIPEFY_SERVICE_ACCOUNT_CLIENT_ID": "<CLIENT_ID>",
        "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET": "<CLIENT_SECRET>"
      }
    }
  }
}
```

Legacy `PIPEFY_OAUTH_CLIENT` / `_SECRET` env vars still resolve to the new `PIPEFY_SERVICE_ACCOUNT_*` names with a one-shot stderr deprecation warning. The `PIPEFY_OAUTH_URL` alias was dropped — set `PIPEFY_BASE_URL` instead.

**CLI (per project)**

```bash
claude mcp add --scope project pipefy \
  -- uv run --directory /absolute/path/to/pipefy-mcp-server pipefy-mcp-server
```

Then (repeat for each key you need, matching [`.env.example`](../.env.example)):

```bash
claude mcp add-env pipefy PIPEFY_SERVICE_ACCOUNT_CLIENT_ID <YOUR_CLIENT_ID>
claude mcp add-env pipefy PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET <YOUR_CLIENT_SECRET>
# Non-prod environments only:
# claude mcp add-env pipefy PIPEFY_BASE_URL https://<your-api-host>
# claude mcp add-env pipefy PIPEFY_AUTH_URL https://<your-signin-host>/realms/<realm>
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
                "PIPEFY_SERVICE_ACCOUNT_CLIENT_ID": "<SERVICE_ACCOUNT_CLIENT_ID>",
                "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET": "<SERVICE_ACCOUNT_CLIENT_SECRET>"
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
