# Shared configuration file (`config.toml`)

`pipefy-sdk` and `pipefy-auth` read an optional TOML file in addition to environment variables. The file lets operators pin defaults (base URLs, org IDs, service-account credentials, ...) per host without exporting shell variables on every invocation.

This page documents the path, schema, and precedence. The file is strictly optional — settings models work with environment variables and their defaults exactly as before when no file exists.

## File path

| Platform | Default location |
|----------|------------------|
| Linux / macOS / other POSIX | `$XDG_CONFIG_HOME/pipefy/config.toml` (falls back to `~/.config/pipefy/config.toml` when `XDG_CONFIG_HOME` is unset) |
| Windows | `%APPDATA%\pipefy\config.toml` (falls back to `~\AppData\Roaming\pipefy\config.toml` when `%APPDATA%` is unset) |

Set `PIPEFY_CONFIG_FILE=/absolute/path/to/foo.toml` to override the default location (useful for tests, ops automation, multi-environment workflows).

The file is **not** auto-created. Missing file = no error; settings use environment variables and field defaults.

## Schema

Top-level keys match pydantic field names on `pipefy_auth.AuthSettings`, `pipefy_sdk.PipefySettings`, and `pipefy_mcp.McpSettings`. The models read the same file; each picks the keys it knows about and ignores the rest. Shared keys (`base_url`, `allow_insecure_urls`) populate both auth and SDK from one entry; the `mcp_*` keys feed the MCP server only.

```toml
# Shared (both AuthSettings and PipefySettings)
base_url = "https://app.pipefy.com"
allow_insecure_urls = false

# Auth (pipefy_auth.AuthSettings)
auth_url = "https://signin.pipefy.com/realms/pipefy"
auth_client_id = "pipefy-cli"
static_token = "..."                   # PIPEFY_TOKEN equivalent
service_account_client_id = "..."
service_account_client_secret = "..."

# SDK (pipefy_sdk.PipefySettings)
org_id = "300123"
service_account_ids = ["42", "43"]
default_webhook_name = "Pipefy Webhook"
permission_denied_enrichment_timeout_seconds = 5.0
gql_reuse_fetched_graphql_schema = false

# MCP server (pipefy_mcp.McpSettings)
unified_envelope = true
remote_mode = false
host = "127.0.0.1"
port = 8000
allow_full_surface_over_http = false
```

Keys use **bare pydantic field names**, not the upper-case `PIPEFY_<NAME>` environment variable names. The env-only aliases (`PIPEFY_TOKEN`, `PIPEFY_OAUTH_CLIENT`, ...) exist to refuse unprefixed environment leakage and do not double as TOML keys.

Unknown keys are silently ignored — pasting both auth and SDK fields into one file is supported and expected.

## Environment variables

The same fields populate from environment variables in upper-case `PIPEFY_<NAME>` form. Env vars feed `pipefy_auth.AuthSettings`, `pipefy_sdk.PipefySettings`, and `pipefy_mcp.McpSettings` independently (each model runs its own loading; auth and SDK additionally run their own SSRF gates and validation). Precedence over TOML and defaults is documented in the next section. A working sample with placeholders lives at [`../.env.example`](../.env.example).

### URL and credential variables

| Variable | Default | Effect |
|----------|---------|--------|
| `PIPEFY_BASE_URL` | `https://app.pipefy.com` | Drives the four API endpoints (`graphql_url`, `internal_api_url`, `interfaces_graphql_url`, `service_account_url`) as computed properties. Set once for non-prod environments. |
| `PIPEFY_AUTH_URL` | `https://signin.pipefy.com/realms/pipefy` | OIDC issuer for `pipefy auth login`. Non-prod realm names don't follow a derivable convention, so this stays a separate full URL. |
| `PIPEFY_SERVICE_ACCOUNT_CLIENT_ID` | unset | Service-account OAuth client id. Required for unattended (CI / MCP server) auth unless `PIPEFY_TOKEN` is set. |
| `PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET` | unset | Companion secret. Treat as sensitive. |
| `PIPEFY_TOKEN` | unset | Static bearer token. Bypasses OAuth entirely. Intended for CI / scripted use; the CLI also accepts `--token`. |
| `PIPEFY_AUTH_CLIENT_ID` | `pipefy-cli` | OIDC client id for the interactive `pipefy auth login` browser flow. Rarely set. |

URL variables must match `https?://` plus non-whitespace and resolve to a public host. `localhost` and RFC1918 ranges are rejected at construction (SSRF policy). Override with `PIPEFY_ALLOW_INSECURE_URLS=true` for local development against non-public hosts.

Credential variables reject leading and trailing whitespace; `PIPEFY_ORG_ID` (below) must be ASCII numeric.

### Optional variables

| Variable | Default | Effect |
|----------|---------|--------|
| `PIPEFY_ORG_ID` | unset | Convenience: pins a default org for CLI and MCP tools that take an optional `org_id` argument. |
| `PIPEFY_SERVICE_ACCOUNT_IDS` | `[]` | Comma-separated list (env-var form) or native TOML array (`service_account_ids = ["42", "43"]`). Guards against accidentally treating service-account users as humans in member-management tools. |
| `PIPEFY_PORTAL_ORG_UUID` | unset | SDK portal integration tests only (`pytest -m integration -k portal`). Set in local `.env` to an organization **UUID** (or numeric org id string) where the active token has **`manage_portals`** (and usually `create_portal`). Never committed; runtime MCP/CLI do not read this. Many default orgs return `PERMISSION_DENIED` on portal writes — pick an org with portal admin scope. See [`mcp/tools/portal.md`](mcp/tools/portal.md#testing). |
| `PIPEFY_DISABLE_STORED_SESSION` | `0` | Set to `1` (or `disable_stored_session = true` in TOML) to skip the keychain-backed stored-session tier entirely. `pipefy auth login` / `auth logout` refuse with exit code 2 when set. |
| `PIPEFY_KEYCHAIN_BACKEND` | `auto` | Set to `file` (or `keychain_backend = "file"` in TOML) to use a file-backed plaintext keyring under `~/.config/pipefy/keyring.cfg` (`%APPDATA%\pipefy\keyring.cfg` on Windows). Unblocks headless Linux and CI runners. Plaintext on disk; opt-in only. |
| `PIPEFY_ALLOW_INSECURE_URLS` | `false` | Disables the SSRF host check on URL variables. Local development only. |
| `PIPEFY_CONFIG_FILE` | unset | Overrides the default `config.toml` path. See [File path](#file-path) above. |

### Legacy aliases

`PIPEFY_OAUTH_CLIENT` and `PIPEFY_OAUTH_SECRET` resolve to `PIPEFY_SERVICE_ACCOUNT_CLIENT_ID` and `PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET` via an alias shim, with a one-shot stderr deprecation warning per legacy key. The aliases will be removed in a later `0.2.0-beta.x` release.

`PIPEFY_OAUTH_URL` is dropped without a replacement. The OAuth token endpoint now derives from `PIPEFY_BASE_URL`.

Full migration notes: [`MIGRATION.md#service-account-env-var-rename`](MIGRATION.md#service-account-env-var-rename).

## Precedence

```
init kwargs > environment variables > .env > config.toml > field defaults
```

Setting `PIPEFY_BASE_URL=https://staging.pipefy.com` in the shell wins over a `base_url = "..."` line in the file. The reverse — file wins over env — is *not* supported: environment is meant for one-off overrides on top of declarative defaults.

## Credentials

Storing OAuth credentials in `config.toml` puts them on disk in plain text. The file is created with the default umask (typically `0o644`); tighten with `chmod 600 ~/.config/pipefy/config.toml` if other users share the host. The recommended channels remain unchanged:

- Interactive user sessions: `pipefy auth login` (token stored in the OS keychain, never in `config.toml`).
- CI / service accounts: shell environment variables, injected by the CI runner's secret manager.
- Local dev: `.env` file in the working directory.

`config.toml` is appropriate when those channels do not fit — e.g. a shared workstation where the user wants a single `base_url` pinned across CLI invocations and the MCP server.

## Relationship to the OS keychain

`config.toml` is hand-edited declarative configuration. It does not hold the user session minted by `pipefy auth login` — that lives in the OS keychain (`StoredSession` JSON keyed by issuer + client ID). The two files coexist under `~/.config/pipefy/`:

```
~/.config/pipefy/
├── config.toml      # operator-edited (this file)
└── refresh.lock     # cross-process refresh lock (auto-managed)
```

A future file-backed keyring backend (#237) will write its credential store as `~/.config/pipefy/keyring.cfg` next to these — a separate file with its own format.
