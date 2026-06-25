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

Two breaking env-var changes in the `0.2.0-beta.x` line are covered below: the `PIPEFY_AUTH_*` namespacing and the service-account rename.

---

## `PIPEFY_AUTH_*` namespacing (breaking)

The interactive-login and keychain env vars are now namespaced under `PIPEFY_AUTH_*`. There is no alias and no grace period: the old names are ignored.

| Old | New | TOML key |
|---|---|---|
| `PIPEFY_AUTH_URL` | `PIPEFY_AUTH_ISSUER_URL` | `issuer_url` (was `auth_url`) |
| `PIPEFY_AUTH_CLIENT_ID` | `PIPEFY_AUTH_CLIENT_ID` (unchanged) | `client_id` (was `auth_client_id`) |
| `PIPEFY_DISABLE_STORED_SESSION` | `PIPEFY_AUTH_DISABLE_STORED_SESSION` | `disable_stored_session` (unchanged) |
| `PIPEFY_KEYCHAIN_BACKEND` | `PIPEFY_AUTH_KEYCHAIN_BACKEND` | `keychain_backend` (unchanged) |

`PIPEFY_AUTH_ISSUER_URL` defaults to `https://signin.pipefy.com/realms/pipefy`. The settings models use `extra="ignore"`, so a stale `PIPEFY_AUTH_URL` / `PIPEFY_DISABLE_STORED_SESSION` / `PIPEFY_KEYCHAIN_BACKEND` is dropped silently (no exception, no warning) and the prod default applies. Audit your shell, `.env`, MCP client JSON, and CI secrets per the table above before upgrading.

---

## Service-account env-var rename (breaking)

The two OAuth 2.0 client-credentials vars used by the service-account auth path are renamed for clarity (and to remove the one-letter footgun against the OIDC user-login issuer):

| Old | New |
|---|---|
| `PIPEFY_OAUTH_URL` | _removed_ — set `PIPEFY_BASE_URL` instead (the OAuth token endpoint derives from `<base>/oauth/token`) |
| `PIPEFY_OAUTH_CLIENT` | `PIPEFY_SERVICE_ACCOUNT_CLIENT_ID` |
| `PIPEFY_OAUTH_SECRET` | `PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET` |

**The legacy `PIPEFY_OAUTH_*` names are removed outright.** There is no alias shim and no deprecation warning. `PIPEFY_OAUTH_CLIENT` and `PIPEFY_OAUTH_SECRET` are ignored if set; the service account stays unconfigured unless you use the new `PIPEFY_SERVICE_ACCOUNT_*` names. `PIPEFY_OAUTH_URL` has no replacement: the OAuth token endpoint derives from `<PIPEFY_BASE_URL>/oauth/token` (default `https://app.pipefy.com/oauth/token`). Set `PIPEFY_BASE_URL` to your API host root for non-prod environments.

When you upgrade:

1. Search-and-replace your shell, `.env`, MCP client JSON, and CI secrets per the table above.
2. Re-run any command (e.g. `pipefy org get --json`) to confirm the credentials still resolve.

`PIPEFY_TOKEN` (static bearer override) is **not** affected.

---

## Settings model split (library / script users only)

End users of `pipefy-cli` and `pipefy-mcp-server` are unaffected — every `PIPEFY_*` env var and `.env` entry keeps loading exactly as before. The split matters only if you construct settings types directly in Python code that depends on `pipefy-sdk`.

Auth-related fields have moved from `PipefySettings` (which now owns endpoint config only) to `pipefy_auth.AuthSettings`. URL endpoints (graphql, internal_api, interfaces, service_account) are now `@computed_field` properties derived from `base_url`:

| Was on `pipefy_sdk.PipefySettings` | Now |
|---|---|
| `graphql_url` (settable) | `@computed_field` on `PipefySettings`, derived from `base_url` |
| `internal_api_url` (settable) | `@computed_field` on `PipefySettings`, derived from `base_url` |
| `interfaces_graphql_url` (settable) | `@computed_field` on `PipefySettings`, derived from `base_url` |
| `service_account_url` (settable) | `@computed_field` on `AuthSettings`, derived from `base_url` |
| `service_account_client_id` | `AuthSettings.service_account_client_id` |
| `service_account_client_secret` | `AuthSettings.service_account_client_secret` |
| (read from env only) | `AuthSettings.issuer_url`, `client_id`, `static_token` |

Because `PipefySettings` / `AuthSettings` are configured with `extra="ignore"`, code that still passes the old kwargs (`PipefySettings(graphql_url=...)`, `AuthSettings(service_account_url=...)`) **silently drops them** — no exception, no warning. Migrate by using `base_url` and composing the two models side by side:

```python
from pipefy_auth import AuthSettings
from pipefy_sdk import PipefySettings

pipefy = PipefySettings(base_url="https://app.pipefy.com")
auth = AuthSettings(
    service_account_client_id="...",
    service_account_client_secret="...",
)
# Computed properties:
pipefy.graphql_url            # "https://app.pipefy.com/graphql"
auth.service_account_url      # "https://app.pipefy.com/oauth/token"
```

If you already build a `pipefy-mcp-server` or `pipefy-cli` settings object, the application-level `Settings` / `CliSettings` already nests both:

```python
from pipefy_mcp.settings import Settings

s = Settings()  # s.pipefy + s.auth, env-loaded
```

The legacy `PIPEFY_OAUTH_*` env-var aliases have been removed from `AuthSettings`; use the `PIPEFY_SERVICE_ACCOUNT_*` names per the rename above.

---

## Questions?

Open an issue at [github.com/pipefy/ai-toolkit/issues](https://github.com/pipefy/ai-toolkit/issues) or email **dev@pipefy.com**.
