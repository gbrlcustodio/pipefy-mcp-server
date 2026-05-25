<div align="center">
  <img
    src="docs/images/pipefy-developers-banner.png"
    alt="Pipefy Developers — Where developers orchestrate intelligence"
    width="100%"
  />
</div>

<p align="center">
  <a href="https://github.com/gbrlcustodio/pipefy-mcp-server/actions/workflows/ci.yml"><img src="https://github.com/gbrlcustodio/pipefy-mcp-server/actions/workflows/ci.yml/badge.svg" alt="CI Status" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+" /></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/uv-package%20manager-blueviolet" alt="uv package manager" /></a>
  <a href="https://modelcontextprotocol.io/introduction"><img src="https://img.shields.io/badge/MCP-Server-orange" alt="MCP Server" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License" /></a>
</p>

# pipefy-labs

Open-source toolkit for **Pipefy** developers: a Model Context Protocol (MCP) server for AI agents, a **`pipefy`** CLI for terminals and automation, a shared GraphQL SDK, and a catalog of agent skill playbooks.

> **Disclaimer:** Community-maintained software for developer workflows. It is not an official Pipefy product or an enterprise support channel.

<p align="center">
  <a href="#overview">Overview</a> •
  <a href="#installation">Installation</a> •
  <a href="#repository-layout">Repository layout</a> •
  <a href="#mcp-server">MCP server</a> •
  <a href="#command-line-interface">CLI</a> •
  <a href="#agent-skills">Agent skills</a> •
  <a href="#documentation">Documentation</a> •
  <a href="#development">Development</a> •
  <a href="#contributing">Contributing</a>
</p>

---

## Overview

| Component | Package / path | Purpose |
|-----------|----------------|---------|
| **MCP server** | `pipefy-mcp-server` | Exposes **128** tools to MCP clients (Cursor, Claude Desktop, Claude Code, and others). |
| **CLI** | `pipefy-cli` | Terminal commands aligned with MCP capabilities; see [`docs/parity.md`](docs/parity.md). |
| **SDK** | `pipefy-sdk` | Vendor GraphQL client, services, and models shared by MCP and CLI. |
| **Skills** | [`skills/`](skills/) | Markdown playbooks (Anthropic Skills format) for common Pipefy workflows. |

Feedback and issues: [GitHub Issues](https://github.com/gbrlcustodio/pipefy-mcp-server/issues) · **dev@pipefy.com**

---

## Installation

### Plugin install (Claude Code)

```text
/plugin marketplace add gbrlcustodio/pipefy-mcp-server
/plugin install pipefy
/pipefy:login
```

`/plugin install pipefy` registers the MCP server (via `uvx --from "git+...#subdirectory=packages/mcp"` with a `--with` chain for the SDK and Auth packages) and the `/pipefy:login` slash command. `/pipefy:login` runs the OAuth browser flow and stores the session in the OS keychain; it persists the Pipefy CLI as a `uv tool install` on first run because `uvx`'s ephemeral binary identity is rejected by the macOS Keychain. A live MCP server picks up the rotated session on its next tool call; if the server failed to start because credentials were missing, restart it (or restart Claude Code) after login completes. Claude Code only; other hosts use the terminal flow below.

Configure the plugin-spawned MCP server's environment by editing the server entry in your Claude Code settings (the `.mcp.json` ships with the plugin and is the source of truth for `command` + `args`; user-supplied `env` is layered on top via Claude Code's settings UI or by editing `~/.claude.json`). `PIPEFY_GRAPHQL_URL` is required; `PIPEFY_INTERNAL_API_URL` is required for AI-automation tools; `PIPEFY_AUTH_URL` is required if you intend to use `/pipefy:login` or the stored-session tier; the service-account triple is only needed for the service-account tier:

```json
{
  "mcpServers": {
    "pipefy": {
      "env": {
        "PIPEFY_GRAPHQL_URL": "https://app.pipefy.com/graphql",
        "PIPEFY_INTERNAL_API_URL": "https://app.pipefy.com/internal_api",
        "PIPEFY_AUTH_URL": "https://signin.pipefy.com/realms/pipefy",
        "PIPEFY_SERVICE_ACCOUNT_URL": "https://app.pipefy.com/oauth/token",
        "PIPEFY_SERVICE_ACCOUNT_CLIENT_ID": "<CLIENT_ID>",
        "PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET": "<CLIENT_SECRET>"
      }
    }
  }
}
```

Note: `/pipefy:login` itself runs `pipefy auth login` in your shell (not in the MCP server process), so `PIPEFY_AUTH_URL` must also be in the shell environment Claude Code was launched from — either exported or in a `.env` file in the CWD. Issue #233 will make `PIPEFY_AUTH_URL` an optional override by baking a CLI-level default. Legacy `PIPEFY_OAUTH_*` aliases still resolve but the CLI prints rename warnings; prefer the canonical `PIPEFY_SERVICE_ACCOUNT_*` names above.

### Pre-1.0 (git)

Installs from this repository use **`uvx`** or **`uv tool install`**. PyPI becomes the canonical source at **v1.0**.

The current public beta line is **`v0.2.0-beta.*`** (first tag: [`v0.2.0-beta.1`](https://github.com/gbrlcustodio/pipefy-mcp-server/releases/tag/v0.2.0-beta.1)), following the standalone [`v0.1.0-beta.1`](https://github.com/gbrlcustodio/pipefy-mcp-server/releases/tag/v0.1.0-beta.1). Pin a tag for reproducible installs:

```sh
uvx --from git+https://github.com/gbrlcustodio/pipefy-mcp-server@v0.2.0-beta.1 --refresh pipefy-mcp-server --help
uvx --from git+https://github.com/gbrlcustodio/pipefy-mcp-server@v0.2.0-beta.1 --refresh pipefy-cli --version
```

**MCP server** (IDE integration):

```sh
uvx --from git+https://github.com/gbrlcustodio/pipefy-mcp-server --refresh pipefy-mcp-server
```

**CLI** (scripts and automation):

```sh
uvx --from git+https://github.com/gbrlcustodio/pipefy-mcp-server --refresh pipefy-cli
```

Permanent install (both packages):

```sh
uv tool install "pipefy-mcp-server @ git+https://github.com/gbrlcustodio/pipefy-mcp-server"
uv tool install "pipefy-cli @ git+https://github.com/gbrlcustodio/pipefy-mcp-server"
```

### Post-1.0 (PyPI)

```sh
uvx pipefy-mcp-server
uv tool install pipefy-cli
```

**Configuration:** environment variables, `.env`, and MCP client samples — **[`docs/setup.md`](docs/setup.md)**.

**Deprecation and semver (post-1.0):** **[`docs/DEPRECATION.md`](docs/DEPRECATION.md)**.

---

## Repository layout

`uv` workspace with three Python packages and a skills catalog. **`pipefy-sdk`** is the vendor GraphQL layer; MCP and CLI depend on it and do not import each other.

| Path | Distribution | Role |
|------|--------------|------|
| [`packages/sdk/`](packages/sdk/) | `pipefy-sdk` | GraphQL transport, services, queries, Pydantic models. [Package README](packages/sdk/README.md) |
| [`packages/mcp/`](packages/mcp/) | `pipefy-mcp-server` | MCP tool registration and server lifecycle. [Package README](packages/mcp/README.md) |
| [`packages/cli/`](packages/cli/) | `pipefy-cli` | Typer CLI (`pipefy` command). [Package README](packages/cli/README.md) |
| [`skills/`](skills/) | — | Agent skill playbooks. [Catalog](skills/README.md) |

---

## MCP server

The server registers **128 tools** across nine domains. Canonical names: `PIPEFY_TOOL_NAMES` in [`packages/mcp/src/pipefy_mcp/tools/registry.py`](packages/mcp/src/pipefy_mcp/tools/registry.py).

Tool descriptions and `Args:` blocks come from Python docstrings (what MCP clients show to models). Per-area reference docs cover parameters, edge cases, and cross-cutting behavior.

**Shared conventions** (pagination, IDs, permissions, error shape): [`docs/mcp/tools/cross-cutting.md`](docs/mcp/tools/cross-cutting.md).

| Domain | Tools | Summary | Reference |
|--------|:-----:|---------|-----------|
| **Pipes & cards** | 37 | Pipes, phases, fields, labels, cards, field conditions, attachments. | [docs](docs/mcp/tools/pipes-and-cards.md) |
| **Database tables** | 17 | Tables, records, schema, table-record attachments. | [docs](docs/mcp/tools/database-tables.md) |
| **Relations** | 8 | Pipe and card relations. | [docs](docs/mcp/tools/relations.md) |
| **Reports** | 17 | Pipe and organization reports, async exports. | [docs](docs/mcp/tools/reports.md) |
| **Automations & AI** | 22 | Automations, AI automations, AI agents, validators. | [docs](docs/mcp/tools/automations-and-ai.md) |
| **Observability** | 10 | Logs, usage, credits, job exports. | [docs](docs/mcp/tools/observability.md) |
| **Members, email & webhooks** | 11 | Membership, inbox email, webhooks. | [docs](docs/mcp/tools/members-email-webhooks.md) |
| **Organization** | 1 | Organization metadata. | [docs](docs/mcp/tools/organization.md) |
| **Introspection** | 5 | Schema discovery and raw GraphQL. | [docs](docs/mcp/tools/introspection.md) |

---

## Command-line interface

The **`pipefy`** CLI mirrors shipped MCP capabilities where parity is defined in **[`docs/parity.md`](docs/parity.md)**. Conventions: Rich output by default, **`--json`** for scripts, **`--yes`** on destructive commands.

```sh
pipefy pipe list --json
pipefy card get 123456789
pipefy introspect query --name getPipe
```

CLI-specific guides: **[`docs/cli/`](docs/cli/README.md)** (including [introspect-then-execute](docs/cli/self-healing.md)).

---

## Agent skills

The [`skills/`](skills/) directory holds workflow playbooks: prerequisites, tool tables (MCP + CLI), steps, and success criteria. Compatible with any agent that reads Markdown (Cursor, Claude Code, Codex, and others).

**Starter pack** (bundled in the CLI):

```sh
pipefy skills list
pipefy skills show pipes-and-cards
```

Full catalog: [`skills/README.md`](skills/README.md). Authoring: [`skills/AGENTS.md`](skills/AGENTS.md). Contributions: [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Documentation

| Document | Description |
|----------|-------------|
| [`docs/README.md`](docs/README.md) | Index by surface (MCP, CLI, SDK). |
| [`docs/setup.md`](docs/setup.md) | Install, `PIPEFY_*` variables, MCP client config. |
| [`docs/parity.md`](docs/parity.md) | MCP tool ↔ CLI command matrix. |
| [`docs/MIGRATION.md`](docs/MIGRATION.md) | Notes for existing MCP users. |
| [`AGENTS.md`](AGENTS.md) | Repository guidelines for contributors and agents. |
| [`RELEASE.md`](RELEASE.md) | Versioning and release process. |

---

## Development

From the repository root:

```bash
uv sync
uv run pytest -m "not integration"    # unit tests (no live API)
uv run pytest -m integration -v     # live API (requires PIPEFY_*)
uv run ruff check . && uv run ruff format .
```

**MCP Inspector** (protocol debugging):

```bash
npx @modelcontextprotocol/inspector uv --directory . run pipefy-mcp-server
```

**Adding an MCP tool:** implement under `packages/mcp/src/pipefy_mcp/tools/`, register in `ToolRegistry`, add the name to `PIPEFY_TOOL_NAMES`, and ship the matching CLI command (or document a deferral in `docs/parity.md`). See [`AGENTS.md`](AGENTS.md) for the full TDD workflow.

---

## Contributing

Contributions are welcome via issues and pull requests.

| Area | How to contribute |
|------|-------------------|
| **Skills** | Markdown only — see [`CONTRIBUTING.md`](CONTRIBUTING.md). |
| **MCP / CLI / SDK** | Follow [`AGENTS.md`](AGENTS.md) and [`docs/parity.md`](docs/parity.md). |
| **Field mapping gaps** | Open an issue with the field type and expected behavior. |
| **Existing MCP setups** | [`docs/MIGRATION.md`](docs/MIGRATION.md) — configuration remains compatible. |
