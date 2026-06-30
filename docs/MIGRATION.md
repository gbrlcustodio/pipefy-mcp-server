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

End users of `pipefy-cli` and `pipefy-mcp-server` are unaffected by the internals; the env contract is the table above. The split below matters only if you construct these types directly in Python.

Each library public API now takes refined value objects (a frozen `pydantic.BaseModel` whose construction witnesses validity) and primitives, never a config instance. The `*Config` readers and the env-reading code are confined to per-package `env.py` submodules behind an optional `[env]` extra, so `import pipefy_sdk` / `import pipefy_auth` pulls no `pydantic-settings`. Host topology and the insecure-URL posture live on one `pipefy_infra.deployment.DeploymentConfig` parsed at the edge; its derived URLs become the value objects the libraries consume.

| Was | Now |
|---|---|
| `pipefy_sdk.SdkConfig` (passed to `PipefyClient`) | `pipefy_sdk.PipefyEndpoints` (`graphql_url` / `interfaces_graphql_url` / `internal_api_url`); `allow_insecure_urls` is a separate primitive arg |
| `SdkConfig.deployment` / `.graphql_url` | build `PipefyEndpoints` from `DeploymentConfig` properties, or call `pipefy_sdk.env.load_sdk(deployment)` |
| `pipefy_auth.AuthConfig` | `pipefy_auth.CredentialSources` (`static_token`, `service_account`, `oidc_client`), passed to `resolve_pipefy_auth` |
| `AuthConfig.to_service_account()` / `ServiceAccountCredentials` | `pipefy_auth.ServiceAccount` (`token_url`, `client_id`, `client_secret`) |
| `AuthConfig.issuer_url` / `public_client_id` | `pipefy_auth.OidcClient` (`issuer_url`, `client_id`) |
| `pipefy_auth.JwtValidationConfig` (injected `deployment`) | `pipefy_auth.JwtValidationInputs` (`issuer_url` required, resolved at the edge) |
| `PipefySettings.org_id` | CLI edge only (`PIPEFY_ORG_ID`, on `CliRuntime`) |
| `PipefySettings.permission_denied_enrichment_timeout_seconds` | MCP edge only (`pipefy_mcp.runtime.McpSettings`) |

Build the value objects directly, or let a loader project them from one `DeploymentConfig`:

```python
from pipefy_auth import CredentialSources, ServiceAccount, resolve_pipefy_auth
from pipefy_sdk import PipefyClient, PipefyEndpoints

endpoints = PipefyEndpoints(
    graphql_url="https://app.pipefy.com/graphql",
    interfaces_graphql_url="https://app.pipefy.com/graphql/interfaces",
    internal_api_url="https://app.pipefy.com/internal_api",
)
auth = resolve_pipefy_auth(
    CredentialSources(
        service_account=ServiceAccount(
            token_url="https://app.pipefy.com/oauth/token",
            client_id="...",
            client_secret="...",
        )
    )
)
client = PipefyClient(endpoints, auth=auth)
```

The `[env]` loaders do this from the environment: `pipefy_infra.env.load_deployment()` parses the deployment, then `pipefy_sdk.env.load_sdk(deployment)` and `pipefy_auth.env.load_auth(deployment)` project the value objects. The application composition roots compose them: `pipefy_cli.runtime.resolve_cli_runtime(...)` and `pipefy_mcp.runtime.resolve_mcp_runtime()` (the MCP server resolves lazily via `get_runtime()`).

---

## Questions?

Open an issue at [github.com/pipefy/ai-toolkit/issues](https://github.com/pipefy/ai-toolkit/issues) or email **dev@pipefy.com**.
