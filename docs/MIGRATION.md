# Migration Guide — v0.1 Cutover (pipefy-mcp-server → pipefy-labs)

Existing users of `pipefy-mcp-server`: this guide covers what changed and what to do. **TL;DR:** almost nothing breaks.

---

## Package name — unchanged

`pipefy-mcp-server` is the same PyPI package name as before. Your `pip install pipefy-mcp-server` or `uvx pipefy-mcp-server` still works. The existing PyPI version is frozen at the pre-monorepo release; new versions ship at v1.0 via the same name.

**Pre-launch (v0.1 → v0.5):** install from git to get the latest:

```sh
uvx --from git+https://github.com/pipefy/ai-toolkit@latest --refresh pipefy-mcp-server
```

---

## MCP client config — unchanged

Your existing Cursor, Claude Desktop, or Claude Code JSON config needs **no changes**. The entry point (`pipefy-mcp-server`) and tool names are identical.

Example Cursor config (still valid):

```json
{
  "mcpServers": {
    "pipefy": {
      "command": "uvx",
      "args": ["pipefy-mcp-server"]
    }
  }
}
```

---

## Tool names and parameters — unchanged

All MCP tools keep the same names, parameters, and behavior as in the pre-monorepo server. No renames, no removed tools. If you have agent prompts or workflows referencing specific tool names, they continue to work.

---

## Repo URL

The toolkit lives in the **Pipefy org** at **[github.com/pipefy/ai-toolkit](https://github.com/pipefy/ai-toolkit)**. Earlier names of this repository (`pipefy-mcp-server`, `pipefy-labs`) may still redirect on GitHub; update remotes and install URLs when you can.

```sh
git remote set-url origin https://github.com/pipefy/ai-toolkit.git
```

Pre-1.0 installs from git:

```sh
uvx --from git+https://github.com/pipefy/ai-toolkit@latest --refresh pipefy-mcp-server
```

---

## New in v0.1

These are new additions — all optional to adopt:

**`pipefy-cli`** — a terminal CLI with the same capabilities as the MCP server.

```sh
uvx --from git+https://github.com/pipefy/ai-toolkit@latest --refresh pipefy-cli
pipefy card get 12345
```

**`skills/` catalog** — Anthropic Skills-format playbooks for common Pipefy workflows, consumable by any LLM agent. Install via [`skills.sh`](https://github.com/vercel-labs/skills):

```sh
npx skills add pipefy/ai-toolkit                           # all skills
npx skills add pipefy/ai-toolkit --skill pipefy-pipes-and-cards
```

---

## Environment variables — mostly unchanged

The same `PIPEFY_*` variables work for both MCP and CLI. A working `.env` for `pipefy-mcp-server` gives you `pipefy-cli` auth immediately. See [`docs/config.md#environment-variables`](config.md#environment-variables) for the full list.

One rename in the upcoming `0.2.0-beta.x` line is covered below.

---

## Auth env-var rename and removed legacy names

The login subsystem is namespaced under `PIPEFY_AUTH_*`; the API credentials stay at the product root (matching `PIPEFY_TOKEN`). These non-namespaced names are gone:

| Removed | Use instead |
|---|---|
| `PIPEFY_OAUTH_URL` | _dropped_. Set `PIPEFY_BASE_URL` (the OAuth token endpoint derives from `<base>/oauth/token`) |
| `PIPEFY_OAUTH_CLIENT` | `PIPEFY_SERVICE_ACCOUNT_CLIENT_ID` |
| `PIPEFY_OAUTH_SECRET` | `PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET` |
| `PIPEFY_AUTH_URL` | `PIPEFY_AUTH_ISSUER_URL` |
| `PIPEFY_AUTH_CLIENT_ID` | `PIPEFY_AUTH_PUBLIC_CLIENT_ID` |
| `PIPEFY_DISABLE_STORED_SESSION` | `PIPEFY_AUTH_DISABLE_STORED_SESSION` |
| `PIPEFY_KEYCHAIN_BACKEND` | `PIPEFY_AUTH_KEYCHAIN_BACKEND` |

**There is no alias shim and no deprecation warning.** A removed name is silently ignored (`extra="ignore"`): an operator who still sets `PIPEFY_OAUTH_CLIENT` gets the unconfigured-tier behavior, and a stale `PIPEFY_AUTH_URL` lets the issuer fall back to the prod default. Search-and-replace your shell, `.env`, MCP client JSON, and CI secrets per the table above.

`PIPEFY_TOKEN` (static bearer override) and `PIPEFY_SERVICE_ACCOUNT_CLIENT_ID` / `_SECRET` keep their names.

---

## Settings architecture (library / script users only)

End users of `pipefy-cli` and `pipefy-mcp-server` are unaffected by the internals; the env contract is the table above. The split below matters only if you construct settings types directly in Python.

The libraries are now pure, env-free `pydantic.BaseModel` value objects (they do not import `pydantic-settings`); the applications own all env reading. Host topology and the insecure-URL posture live on one `pipefy_infra.deployment.DeploymentConfig`, injected by reference into the SDK and auth configs so they cannot diverge.

| Was | Now |
|---|---|
| `pipefy_sdk.PipefySettings` | `pipefy_sdk.SdkConfig` (required injected `deployment`) |
| `PipefySettings.base_url` / `allow_insecure_urls` | `DeploymentConfig.base_url` / `allow_insecure_urls` (forwarded on `SdkConfig`) |
| `pipefy_auth.AuthSettings` | `pipefy_auth.AuthConfig` (required injected `deployment`) |
| `AuthSettings.auth_url` / `auth_client_id` | `AuthConfig.issuer_url` / `public_client_id` |
| `AuthSettings.service_account_url` | `deployment.oauth_token_url` |
| `service_account_client_id` / `_secret` (flat) | nested `AuthConfig.service_account` (a `ServiceAccountCredentials`, or `None`) |
| `pipefy_auth.JwtValidationSettings` | `pipefy_auth.JwtValidationConfig` (required injected `deployment`) |
| `PipefySettings.org_id` | CLI edge only (`PIPEFY_ORG_ID`) |
| `PipefySettings.permission_denied_enrichment_timeout_seconds` | MCP edge only (`pipefy_mcp.McpSettings`) |

Compose by building one `DeploymentConfig` and injecting it:

```python
from pipefy_auth import AuthConfig, ServiceAccountCredentials
from pipefy_infra.deployment import DeploymentConfig
from pipefy_sdk import SdkConfig

deployment = DeploymentConfig(base_url="https://app.pipefy.com")
sdk = SdkConfig(deployment=deployment)
auth = AuthConfig(
    deployment=deployment,
    service_account=ServiceAccountCredentials(client_id="...", client_secret="..."),
)
sdk.graphql_url               # "https://app.pipefy.com/graphql"
auth.to_service_account().token_url  # "https://app.pipefy.com/oauth/token"
```

The application composition roots do this for you from the environment: `pipefy_cli.config.resolve_cli_settings(...)` and `pipefy_mcp.settings.resolve_mcp_settings()` (the MCP server resolves lazily via `get_settings()`).

---

## Questions?

Open an issue at [github.com/pipefy/ai-toolkit/issues](https://github.com/pipefy/ai-toolkit/issues) or email **dev@pipefy.com**.
