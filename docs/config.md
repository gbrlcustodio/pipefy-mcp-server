# Shared configuration file (`config.toml`)

`pipefy` and `pipefy-auth` read an optional TOML file in addition to environment variables. The file lets operators pin defaults (base URLs, org IDs, service-account credentials, ...) per host without exporting shell variables on every invocation.

This page documents the path, schema, and precedence. The file is strictly optional — settings models work with environment variables and their defaults exactly as before when no file exists.

## File path

| Platform | Default location |
|----------|------------------|
| Linux / macOS / other POSIX | `$XDG_CONFIG_HOME/pipefy/config.toml` (falls back to `~/.config/pipefy/config.toml` when `XDG_CONFIG_HOME` is unset) |
| Windows | `%APPDATA%\pipefy\config.toml` (falls back to `~\AppData\Roaming\pipefy\config.toml` when `%APPDATA%` is unset) |

Set `PIPEFY_CONFIG_FILE=/absolute/path/to/foo.toml` to override the default location (useful for tests, ops automation, multi-environment workflows).

The file is **not** auto-created. Missing file = no error; settings use environment variables and field defaults.

## Schema

Top-level keys match pydantic field names on `pipefy_auth.AuthSettings`, `pipefy_sdk.PipefySettings`, and `pipefy_mcp.McpSettings`. Each settings class reads the same file, picks the keys it knows about, and ignores the rest. Shared keys (`base_url`, `allow_insecure_urls`) populate both auth and SDK from one entry; the MCP keys (`unified_envelope`, `remote_mode`, `host`, `port`) feed the MCP server only.

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
default_webhook_name = "Pipefy Webhook"
permission_denied_enrichment_timeout_seconds = 5.0
gql_reuse_fetched_graphql_schema = false

# MCP server (pipefy_mcp.McpSettings)
unified_envelope = true
remote_mode = false
host = "127.0.0.1"
port = 8000
log_level = "INFO"
# allowed_hosts / allowed_origins are optional; unset derives the allowlist from
# the resource-server URL. Set them only for extra proxied hostnames.
allowed_hosts = ["mcp.pipefy.com"]
allowed_origins = ["https://mcp.pipefy.com"]
```

Keys use **bare pydantic field names**, not the upper-case `PIPEFY_<NAME>` environment variable names. The env-only aliases (`PIPEFY_TOKEN`, `PIPEFY_OAUTH_CLIENT`, ...) exist to refuse unprefixed environment leakage and do not double as TOML keys.

Unknown keys are silently ignored — pasting both auth and SDK fields into one file is supported and expected.

## Environment variables

The same fields populate from environment variables in upper-case `PIPEFY_<NAME>` form. Env vars feed `pipefy_auth.AuthSettings`, `pipefy_sdk.PipefySettings`, and `pipefy_mcp.McpSettings` independently (each settings class runs its own loading; auth and SDK additionally run their own SSRF gates and validation). Precedence over TOML and defaults is documented in the next section. A working sample with placeholders lives at [`../.env.example`](../.env.example).

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

## MCP server (`pipefy-mcp-server`)

These variables load into `pipefy_mcp.McpSettings` (`settings.mcp`). TOML keys use the bare field names under the same top-level file (see [Schema](#schema)).

| Variable | Default | Effect |
|----------|---------|--------|
| `PIPEFY_MCP_PROFILE` | `local` | Launch profile: `local` registers every tool; `remote` exposes only remote-safe tools and validates an inbound bearer per request. |
| `PIPEFY_MCP_TOOLSETS` | unset | Comma-separated toolset names to expose, applied after the remote floor to narrow the surface (selection only ever narrows, never widens past the floor). Names are **subject domains** (`workflow`, `database`, `interfaces`, `automation`, `intelligence`, `analytics`, `governance`, `integration`) and/or **persona profiles** (`requester`, `operator`, `manager`, `builder`, `admin`, `auditor`), unioned. `all` / `default` or unset keep every tool — and mixing either keyword with a domain or profile (e.g. `default,workflow`) still keeps every tool, since the no-curation keyword wins. `power` (alias `architect`) instead hides the curated tools behind four catalog meta-tools (`search_tools`, `describe_tool`, `execute_tool`, `get_tool_categories`) plus the raw-GraphQL tools, for clients that discover on demand — and co-listing `power` with a domain or profile applies the full power profile (`power` wins). An unknown name is a startup error. Also settable with `--toolsets` / `--tools`. |
| `PIPEFY_MCP_TRANSPORT` | derived from profile | `stdio` or `http`. Unset: `local` → `stdio`, `remote` → `http`. |
| `PIPEFY_MCP_HOST` | `127.0.0.1` | HTTP bind host. The unauthenticated `local` profile refuses a non-loopback bind unless `PIPEFY_MCP_ALLOW_INSECURE_HTTP_BIND` is set; the authenticated `remote` profile binds any host. |
| `PIPEFY_MCP_PORT` | `8000` | HTTP bind port. |
| `PIPEFY_MCP_ALLOW_INSECURE_HTTP_BIND` | `false` | Escape hatch: lets the unauthenticated `local` profile serve HTTP on a non-loopback host, exposing the full tool surface with no inbound bearer. The `remote` profile never needs it. |
| `PIPEFY_MCP_ALLOWED_HOSTS` | unset | JSON array of extra `Host` header values the HTTP transport accepts for DNS-rebinding protection, on top of loopback and the `PIPEFY_MCP_RS_RESOURCE_SERVER_URL` host. Unset derives the allowlist from the resource-server URL, so a proxied deployment usually needs none; set it only when a proxy forwards a public `Host` that differs. An entry matches an exact `Host` or, as `host:*`, any port. These are extra entries, so an empty array behaves like unset (the resource-server host is still derived). |
| `PIPEFY_MCP_ALLOWED_ORIGINS` | unset | JSON array overriding the derived `scheme://host` `Origin` allowlist. Unset derives `http`/`https` origins from the allowed hosts; a non-empty array replaces them with a custom set (e.g. `https`-only); an empty array is the strictest override, rejecting any request that sends an `Origin` header (a request with no `Origin` still passes). |
| `PIPEFY_MCP_UNIFIED_ENVELOPE` | `true` | When true, migrated tools return `{success, data, ...}`. |
| `PIPEFY_MCP_LOG_LEVEL` | `INFO` | Governs the root logger the MCP SDK configures (RichHandler text on **stderr**) only; it is passed to `MCPServer(log_level=...)` and to uvicorn on the HTTP path. Accepts `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` (case-insensitive). Hosted structured JSON request/tool lines use a dedicated logger pinned at `INFO` on stderr, so raising this knob to quiet text logs does **not** drop those debugging events. Structured lines stay on stderr so they never share the stdio JSON-RPC stdout channel. |

### iPaaS (Advanced Automations)

These variables load into `pipefy_mcp.IpaasSettings` (`settings.ipaas`) and back the iPaaS tools (see [`mcp/tools/ipaas.md`](mcp/tools/ipaas.md)). They work **out of the box**: the default OAuth client is Pipefy's canonical *public* PKCE client on the production iPaaS host — a publishable identifier (like the `pipefy-cli` OIDC client), not a secret; authorization is carried by the caller's pipe-scoped session, never by the client identity.

| Variable | Default | Effect |
|----------|---------|--------|
| `PIPEFY_IPAAS_URL` | `https://ipaas.pipefy.com` | Base URL of the iPaaS (Advanced Automations) host. Override for staging or single-tenant deployments. |
| `PIPEFY_IPAAS_OAUTH_CLIENT_ID` | canonical public client | OAuth client id on the iPaaS host. Override alongside a custom host; set blank to disable the iPaaS tools (they then answer with a clear "disabled" error). |
| `PIPEFY_IPAAS_OAUTH_CLIENT_SECRET` | unset | Only for a confidential (`client_secret_post`) registration; the default public client has none. Treat as a secret. |
| `PIPEFY_IPAAS_OAUTH_REDIRECT_URI` | `https://localhost/pipefy-mcp-callback` | Must byte-match a redirect URI registered on the OAuth client. Never actually followed (the flow is headless). |
| `PIPEFY_IPAAS_CONNECTION_<NAME>` | unset | Not a setting — a per-credential convention read at call time by `create_ipaas_connection`: a `value` prop given as `{"$env": "PIPEFY_IPAAS_CONNECTION_<NAME>"}` resolves to this variable, so app secrets never enter the conversation. Only variables under this prefix resolve. Set it in the MCP server's environment (e.g. the `env` block of its client configuration) before launch. Locally-run (`local`-profile) servers only: the hosted `remote` profile rejects `$env` references, whose values would be shared by every caller. |
