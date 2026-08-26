# pipefy-cli

Typer-based CLI for Pipefy. Exposes all MCP tool capabilities as terminal commands and scripts. Depends on [`pipefy`](../sdk/README.md) for GraphQL calls.

## Install

```sh
uvx --from pipefy-cli pipefy --help
```

Or persistently:

```sh
uv tool install pipefy-cli
```

`pipefy-cli` and its dependencies (`pipefy`, `pipefy-auth`) are published to PyPI, so `uv` resolves the whole set from there. While the toolkit ships only pre-release versions (the 0.x line), `uv` resolves the latest pre-release automatically; once a stable release exists it resolves that instead. Do not pass a global `--prerelease allow`: it also lets transitive dependencies jump to their own pre-releases, which can pull a broken build. The console script is `pipefy`, so `uvx --from pipefy-cli` runs it as `pipefy`.

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

1. **Interactive (`pipefy auth login`)** — browser OAuth flow, session stored in the OS keychain by default (`PIPEFY_KEYCHAIN_BACKEND=file` or `encrypted` select other stores). Best for human developers. Status and revocation via `pipefy auth status` and `pipefy auth logout`.
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
