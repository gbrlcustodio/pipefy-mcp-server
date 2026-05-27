# Shared configuration file (`config.toml`)

`pipefy-sdk` and `pipefy-auth` read an optional TOML file in addition to
environment variables. The file lets operators pin defaults (base URLs,
org IDs, service-account credentials, ...) per host without exporting
shell variables on every invocation.

This page documents the path, schema, and precedence. The file is
strictly optional — settings models work with environment variables and
their defaults exactly as before when no file exists.

## File path

| Platform | Default location |
|----------|------------------|
| Linux / macOS / other POSIX | `$XDG_CONFIG_HOME/pipefy/config.toml` (falls back to `~/.config/pipefy/config.toml` when `XDG_CONFIG_HOME` is unset) |
| Windows | `%APPDATA%\pipefy\config.toml` (falls back to `~\AppData\Roaming\pipefy\config.toml` when `%APPDATA%` is unset) |

Set `PIPEFY_CONFIG_FILE=/absolute/path/to/foo.toml` to override the
default location (useful for tests, ops automation, multi-environment
workflows).

The file is **not** auto-created. Missing file = no error; settings use
environment variables and field defaults.

## Schema

Top-level keys match pydantic field names on `pipefy_auth.AuthSettings`
and `pipefy_sdk.PipefySettings`. The two models read the same file; each
picks the keys it knows about and ignores the rest. Shared keys
(`base_url`, `allow_insecure_urls`) populate both models from one entry.

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
mcp_unified_envelope = true
```

Keys use **bare pydantic field names**, not the upper-case
`PIPEFY_<NAME>` environment variable names. The env-only aliases
(`PIPEFY_TOKEN`, `PIPEFY_OAUTH_CLIENT`, ...) exist to refuse unprefixed
environment leakage and do not double as TOML keys.

Unknown keys are silently ignored — pasting both auth and SDK fields
into one file is supported and expected.

## Precedence

```
init kwargs > environment variables > .env > config.toml > field defaults
```

Setting `PIPEFY_BASE_URL=https://staging.pipefy.com` in the shell wins
over a `base_url = "..."` line in the file. The reverse — file wins
over env — is *not* supported: environment is meant for one-off
overrides on top of declarative defaults.

## Credentials

Storing OAuth credentials in `config.toml` puts them on disk in plain
text. The file is created with the default umask (typically `0o644`);
tighten with `chmod 600 ~/.config/pipefy/config.toml` if other users
share the host. The recommended channels remain unchanged:

- Interactive user sessions: `pipefy auth login` (token stored in the
  OS keychain, never in `config.toml`).
- CI / service accounts: shell environment variables, injected by the
  CI runner's secret manager.
- Local dev: `.env` file in the working directory.

`config.toml` is appropriate when those channels do not fit — e.g. a
shared workstation where the user wants a single `base_url` pinned
across CLI invocations and the MCP server.

## Relationship to the OS keychain

`config.toml` is hand-edited declarative configuration. It does not
hold the user session minted by `pipefy auth login` — that lives in
the OS keychain (`StoredSession` JSON keyed by issuer + client ID).
The two files coexist under `~/.config/pipefy/`:

```
~/.config/pipefy/
├── config.toml      # operator-edited (this file)
└── refresh.lock     # cross-process refresh lock (auto-managed)
```

A future file-backed keyring backend (#237) will write its credential
store as `~/.config/pipefy/keyring.cfg` next to these — a separate
file with its own format.
