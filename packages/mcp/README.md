# pipefy-mcp-server

MCP server for Pipefy — **187 tools** for AI agents (Cursor, Claude Desktop, Claude Code, Codex, and any MCP-compatible client). Depends on [`pipefy`](../sdk/README.md) for all GraphQL and API logic.

## Install

```sh
uvx pipefy-mcp-server
```

`pipefy-mcp-server` and its workspace dependencies (`pipefy`, `pipefy-auth`, `pipefy-infra`) are published to PyPI, so `uvx` resolves the whole set from there. While the toolkit ships only pre-release versions (the 0.x line), `uvx` resolves the latest pre-release automatically; once a stable release exists it resolves that instead. Do not pass a global `--prerelease allow`: it also lets transitive dependencies jump to their own pre-releases, which can pull a broken build.

For per-client wiring (Claude Code / Cursor / Claude Desktop / Codex), see [root `README.md#installation`](../../README.md#installation).

## Uninstall

`./uninstall.sh --scan` (repository root) reports every Pipefy MCP registration on the machine, matched on what each one runs rather than on its name, plus the tools, credentials, skills, and plugin state behind them. A bare run removes what you approve, in tiers. Teardown reference and the hosted / local / plugin switching recipes: [`docs/uninstall.md`](../../docs/uninstall.md).

## Configuration

Set the following environment variables (or add them to a `.env` file in the working directory, or pin them in `~/.config/pipefy/config.toml`):

```env
PIPEFY_SERVICE_ACCOUNT_CLIENT_ID=your_client_id
PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET=your_client_secret
# Non-prod environments only:
# PIPEFY_BASE_URL=https://<your-api-host>
# PIPEFY_AUTH_URL=https://<your-signin-host>/realms/<realm>
```

`PIPEFY_BASE_URL` defaults to `https://app.pipefy.com` (drives the four API endpoints) and `PIPEFY_AUTH_URL` defaults to `https://signin.pipefy.com/realms/pipefy` (the OIDC issuer). Set them only for non-prod environments.

Full reference (every `PIPEFY_*` variable, validation rules, TOML schema, precedence chain): [`docs/config.md`](../../docs/config.md).

## Edge cases and alternative wiring

### macOS keychain `errSecInvalidOwnerEdit (-25244)`

`pipefy auth login` may exit with `errSecInvalidOwnerEdit (-25244)` ("Invalid attempt to change the owner of this item") at the final keychain-write step even though OAuth itself succeeded. Prefer `PIPEFY_KEYCHAIN_BACKEND=encrypted` so the rotating session is not stored as a Keychain item. Otherwise clear the entry with `pipefy auth logout` (or `security delete-generic-password -s pipefy`) and run `pipefy auth login` from Terminal.app, clicking **Always Allow** if prompted. `PIPEFY_KEYCHAIN_BACKEND=file` or a static `PIPEFY_TOKEN` remain the no-OS-keychain escapes. See [`docs/cli/auth.md`](../../docs/cli/auth.md) for the full platform-specific troubleshooting.

### Claude Code: `claude mcp add` (per-project terminal flow)

Useful when you want to wire the server without editing `~/.claude.json` by hand.

**Hosted MCP (HTTP)** — zero local Python; OAuth in Claude Code. Prefer this when you do not need the full local tool surface. Do not also install the Claude Code plugin under the same server name. Canonical snippet: [root README — Hosted MCP](../../README.md#1-hosted-mcp-claude-code).

**Local stdio** — runs `uvx pipefy-mcp-server` on the machine:

```bash
claude mcp add --scope project pipefy \
  -- uvx pipefy-mcp-server
```

Then (repeat for each key you need; service-account path):

```bash
claude mcp add-env pipefy PIPEFY_SERVICE_ACCOUNT_CLIENT_ID <YOUR_CLIENT_ID>
claude mcp add-env pipefy PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET <YOUR_CLIENT_SECRET>
# Non-prod environments only:
# claude mcp add-env pipefy PIPEFY_BASE_URL https://<your-api-host>
# claude mcp add-env pipefy PIPEFY_AUTH_URL https://<your-signin-host>/realms/<realm>
```

### Claude Code: settings edit (post-plugin install)

The plugin's `.mcp.json` is the hosted URL (`https://mcp.pipefy.com/mcp`) with in-client OAuth — the same file the Cursor plugin points at. Do not also register a local stdio `pipefy` server under the same name. To run local stdio instead, uninstall the plugin (or disable its server) and use `claude mcp add` in the section above.

### Local-clone alternative (contributors)

If you have a clone of this repo and want the MCP server to use it directly (without `uvx` fetching from git), launch via `uv run` from the clone:

```json
{
  "mcpServers": {
    "pipefy": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/pipefy-mcp-server",
        "pipefy-mcp-server"
      ],
      "env": {
        "PIPEFY_SERVICE_ACCOUNT_CLIENT_ID": "<CLIENT_ID>",
        "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET": "<CLIENT_SECRET>"
      }
    }
  }
}
```

This form also works as a per-project `.mcp.json` if your team shares a clone. Committing `.mcp.json` without secrets (placeholders or env injection) keeps team setups consistent.

### Legacy environment variables

`PIPEFY_OAUTH_CLIENT` and `PIPEFY_OAUTH_SECRET` still resolve to the new `PIPEFY_SERVICE_ACCOUNT_*` names with a one-shot stderr deprecation warning. The aliases will be removed in a later `0.2.0-beta.x` release. The `PIPEFY_OAUTH_URL` alias was dropped — set `PIPEFY_BASE_URL` instead. Migration notes: [`docs/MIGRATION.md#service-account-env-var-rename`](../../docs/MIGRATION.md#service-account-env-var-rename).

## Tools

**187 tools** across fourteen domains (including **Portals**) — see the root [`README.md`](../../README.md#mcp-server) for the full table with per-area links. Deep reference: [`docs/mcp/tools/`](../../docs/mcp/tools/cross-cutting.md) (start with [`cross-cutting.md`](../../docs/mcp/tools/cross-cutting.md)); portals: [`portal.md`](../../docs/mcp/tools/portal.md).

## Development

From the **repository root**:

```bash
uv sync
uv run pytest packages/mcp/tests     # MCP tests in isolation
uv run ruff check packages/mcp/src   # lint
```

See the root [`README.md`](../../README.md) and [`AGENTS.md`](../../AGENTS.md) for contributor guidance.
