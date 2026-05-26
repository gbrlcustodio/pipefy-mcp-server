# pipefy-cli

Typer-based CLI for Pipefy. Exposes all MCP tool capabilities as terminal commands and scripts. Depends on [`pipefy-sdk`](../sdk/README.md) for GraphQL calls.

## Install (pre-launch, v0.1 → v0.5)

```sh
uvx --from git+https://github.com/<owner>/pipefy-labs --refresh pipefy-cli
```

> At v1.0 this moves to `uv tool install pipefy-cli` from PyPI.

## Quick start

```bash
# Show all commands
pipefy --help

# Card operations
pipefy card get 12345 --json
pipefy card list --pipe 67890
pipefy card create --pipe 67890 --title "New card"

# Skills catalog
pipefy skills list
pipefy skills show pipes-and-cards | pbcopy
```

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

Full guide: [`docs/setup.md`](../../docs/setup.md). CLI-focused docs: [`docs/cli/`](../../docs/cli/README.md).

Use `PIPEFY_TOKEN` (or `--token`) for a direct bearer token instead of service-account credentials.

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
