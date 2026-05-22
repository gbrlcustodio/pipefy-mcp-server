# Migration Guide — v0.1 Cutover (pipefy-mcp-server → pipefy-labs)

Existing users of `pipefy-mcp-server`: this guide covers what changed and what to do. **TL;DR:** almost nothing breaks.

---

## Package name — unchanged

`pipefy-mcp-server` is the same PyPI package name as before. Your `pip install pipefy-mcp-server` or `uvx pipefy-mcp-server` still works. The existing PyPI version is frozen at the pre-monorepo release; new versions ship at v1.0 via the same name.

**Pre-launch (v0.1 → v0.5):** install from git to get the latest:

```sh
uvx --from git+https://github.com/<owner>/pipefy-labs --refresh pipefy-mcp-server
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

The repository was renamed from `pipefy-mcp-server` to `pipefy-labs` on GitHub. GitHub preserves redirects — your existing `git remote` URLs for the old repo keep working for `git fetch`, `git pull`, and `git push`.

Update your remote at your convenience:

```sh
git remote set-url origin https://github.com/<owner>/pipefy-labs.git
```

---

## New in v0.1

These are new additions — all optional to adopt:

**`pipefy-cli`** — a terminal CLI with the same capabilities as the MCP server.

```sh
uvx --from git+https://github.com/<owner>/pipefy-labs --refresh pipefy-cli
pipefy card get 12345
pipefy skills list
```

**`skills/` catalog** — Anthropic Skills-format playbooks for common Pipefy workflows, consumable by any LLM agent.

```sh
pipefy skills show pipes-and-cards | pbcopy   # paste into agent context
```

---

## Environment variables — mostly unchanged

The same `PIPEFY_*` variables work for both MCP and CLI. A working `.env` for `pipefy-mcp-server` gives you `pipefy-cli` auth immediately. See [`docs/setup.md`](setup.md) for the full list.

One rename in the upcoming `0.2.0-beta.x` line is covered below.

---

## Service-account env-var rename

The three OAuth 2.0 client-credentials vars used by the service-account auth path are being renamed for clarity (and to remove the one-letter footgun against `PIPEFY_AUTH_URL`, the new OIDC user-login issuer):

| Old | New |
|---|---|
| `PIPEFY_OAUTH_URL` | `PIPEFY_SERVICE_ACCOUNT_URL` |
| `PIPEFY_OAUTH_CLIENT` | `PIPEFY_SERVICE_ACCOUNT_CLIENT_ID` |
| `PIPEFY_OAUTH_SECRET` | `PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET` |

**No immediate action required.** The legacy names are still honored — `PIPEFY_OAUTH_*` env vars and `oauth_*` keys in `~/.config/pipefy/config.toml` both flow through an alias shim and populate the renamed fields. The first command run with a legacy name set prints a one-shot stderr deprecation warning per legacy key still in use; the message names the replacement.

When you're ready to update:

1. Search-and-replace your shell, `.env`, MCP client JSON, CI secrets, and any `~/.config/pipefy/config.toml` per the table above.
2. Optionally re-run any command (e.g. `pipefy org get --json`) to confirm the deprecation warning is gone.

The legacy names will be removed in a later `0.2.0-beta.x` release; the change will carry an explicit breaking-change callout in the changelog at that time.

`PIPEFY_TOKEN` (static bearer override) and `PIPEFY_AUTH_URL` / `PIPEFY_AUTH_CLIENT_ID` (interactive user-login flow) are **not** affected.

---

## Settings model split (library / script users only)

End users of `pipefy-cli` and `pipefy-mcp-server` are unaffected — every `PIPEFY_*` env var, `.env` entry, and `~/.config/pipefy/config.toml` key keeps loading exactly as before. The split matters only if you construct settings types directly in Python code that depends on `pipefy-sdk`.

Auth-related fields have moved from `PipefySettings` (which now owns endpoint config only) to a new `pipefy_auth.AuthSettings`:

| Was on `pipefy_sdk.PipefySettings` | Now on `pipefy_auth.AuthSettings` |
|---|---|
| `service_account_url` | `service_account_url` |
| `service_account_client_id` | `service_account_client_id` |
| `service_account_client_secret` | `service_account_client_secret` |
| (read from env only) | `auth_url`, `auth_client_id`, `static_token` |

Because `PipefySettings` is configured with `extra="ignore"`, code like `PipefySettings(service_account_url=...)` **silently drops the credentials** — no exception, no warning. Migrate by composing the two models side by side:

```python
from pipefy_auth import AuthSettings
from pipefy_sdk import PipefySettings

pipefy = PipefySettings(graphql_url="https://app.pipefy.com/graphql")
auth = AuthSettings(
    service_account_url="https://app.pipefy.com/oauth/token",
    service_account_client_id="...",
    service_account_client_secret="...",
)
```

If you already build a `pipefy-mcp-server` or `pipefy-cli` settings object, the application-level `Settings` / `CliSettings` already nests both:

```python
from pipefy_mcp.settings import Settings

s = Settings()  # s.pipefy + s.auth, env-loaded
```

The legacy `PIPEFY_OAUTH_*` env-var aliases and the deprecation warning live on `AuthSettings`; behaviour is preserved through the rename window above.

---

## Questions?

Open an issue at [github.com/<owner>/pipefy-labs/issues](https://github.com/<owner>/pipefy-labs/issues) or email **dev@pipefy.com**.
