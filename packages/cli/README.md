# pipefy-cli

Typer-based CLI for Pipefy. Exposes all MCP tool capabilities as terminal commands and scripts. Depends on [`pipefy-sdk`](../sdk/README.md) for GraphQL calls.

## Install (pre-launch, v0.1 → v0.5)

```sh
uvx \
  --with "pipefy-sdk @ git+https://github.com/gbrlcustodio/pipefy-mcp-server#subdirectory=packages/sdk" \
  --with "pipefy-auth @ git+https://github.com/gbrlcustodio/pipefy-mcp-server#subdirectory=packages/auth" \
  --from "git+https://github.com/gbrlcustodio/pipefy-mcp-server#subdirectory=packages/cli" \
  --refresh pipefy-cli
```

Or persistently:

```sh
uv tool install \
  --with "pipefy-sdk @ git+https://github.com/gbrlcustodio/pipefy-mcp-server#subdirectory=packages/sdk" \
  --with "pipefy-auth @ git+https://github.com/gbrlcustodio/pipefy-mcp-server#subdirectory=packages/auth" \
  "git+https://github.com/gbrlcustodio/pipefy-mcp-server#subdirectory=packages/cli"
```

The `--with` flags are required pre-1.0 because the workspace members are not yet on PyPI. At v1.0 this collapses to `uv tool install pipefy-cli`.

## Quick start

```bash
# Show all commands
pipefy --help

# Card operations
pipefy card get 12345 --json
pipefy card list --pipe 67890
pipefy card create --pipe 67890 --title "New card"
```

Agent skills are installed separately via [`skills.sh`](https://github.com/vercel-labs/skills); see [`skills/README.md`](../../skills/README.md).

## Configuration

Same `PIPEFY_*` environment variables as `pipefy-mcp-server` (`.env` in CWD is loaded automatically):

```env
PIPEFY_SERVICE_ACCOUNT_CLIENT_ID=your_client_id
PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET=your_client_secret
# Non-prod environments only:
# PIPEFY_BASE_URL=https://<your-api-host>
# PIPEFY_AUTH_URL=https://<your-signin-host>/realms/<realm>
```

`PIPEFY_BASE_URL` defaults to `https://app.pipefy.com` (drives the four API endpoints) and `PIPEFY_AUTH_URL` defaults to `https://signin.pipefy.com/realms/pipefy` (the OIDC issuer). Set them only for non-prod environments.

### Authentication paths

Three credential sources, in CLI precedence order:

1. **Interactive (`pipefy auth login`)** — browser OAuth flow, session stored in the OS keychain. Best for human developers. Status and revocation via `pipefy auth status` and `pipefy auth logout`.
2. **Static bearer (`PIPEFY_TOKEN` or `--token`)** — direct bearer token, no OAuth. Intended for CI and scripted use. Overrides everything else.
3. **Service-account OAuth (`PIPEFY_SERVICE_ACCOUNT_CLIENT_ID` + `PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET`)** — unattended OAuth client-credentials grant. Used by the MCP server.

Full env-var reference, validation rules, and `config.toml` precedence: [`docs/config.md`](../../docs/config.md). Auth deep-dive (precedence rules, troubleshooting, keychain backends): [`docs/cli/auth.md`](../../docs/cli/auth.md).

## Output modes

Every command defaults to **Rich-formatted** human output. Add `--json` for machine-readable JSON to stdout.

```bash
pipefy card get 12345 --json | jq '.title'
```

## Parity with MCP

Every MCP tool has a CLI counterpart (or a tracked deferral). See [`docs/parity.md`](../../docs/parity.md) for the full matrix.

## Shell completion

```bash
pipefy --install-completion bash    # or zsh, fish, etc.
```

## Development

From the **repository root**:

```bash
uv sync
uv run pytest packages/cli/tests     # CLI tests
uv run ruff check packages/cli/src   # lint
```

See [`AGENTS.md`](../../AGENTS.md) and [`CLAUDE.md`](../../CLAUDE.md) for contributor guidance.
