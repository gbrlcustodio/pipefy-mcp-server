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

> Pre-1.0 ships from this git repo via `uvx` and `uv tool install`. PyPI becomes the canonical source at **v1.0**. The current beta line is **`v0.2.0-beta.*`** (first tag: [`v0.2.0-beta.1`](https://github.com/gbrlcustodio/pipefy-mcp-server/releases/tag/v0.2.0-beta.1)). Every snippet below pins **`@latest`** — a moving git tag the release flow updates to point at the most recent release. To pin a specific version, swap `@latest` for a version tag (e.g. `@v0.2.0-beta.1`).
>
> The `--with pipefy-sdk @ ...#subdirectory=packages/sdk` / `pipefy-auth @ ...#subdirectory=packages/auth` flags are required pre-1.0: this repo is a uv workspace, and the workspace members are not yet published to PyPI, so uv needs them named explicitly. The flags go away at v1.0 (PyPI install).

Service-account credentials (`PIPEFY_SERVICE_ACCOUNT_CLIENT_ID` and `PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET`) are the unattended auth path used by the MCP server and CI scripts. The CLI additionally supports interactive `pipefy auth login` (browser OAuth, session in OS keychain). Full env-var reference and `config.toml` precedence: [`docs/config.md`](docs/config.md).

### MCP client wiring

#### Claude Code

```text
/plugin marketplace add gbrlcustodio/pipefy-mcp-server
/plugin install pipefy
/pipefy:install
/pipefy:login
```

`/plugin install pipefy` registers the MCP server and the `/pipefy:install` + `/pipefy:login` slash commands. `/pipefy:install` runs `uv tool install` once to put `pipefy` on PATH (idempotent). `/pipefy:login` runs the OAuth browser flow. For terminal-driven setups or per-project `.mcp.json`, see [`packages/mcp/README.md`](packages/mcp/README.md).

#### Cursor

Edit `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (per project):

```json
{
  "mcpServers": {
    "pipefy": {
      "command": "uvx",
      "args": [
        "--with",
        "pipefy-sdk @ git+https://github.com/gbrlcustodio/pipefy-mcp-server@latest#subdirectory=packages/sdk",
        "--with",
        "pipefy-auth @ git+https://github.com/gbrlcustodio/pipefy-mcp-server@latest#subdirectory=packages/auth",
        "--from",
        "git+https://github.com/gbrlcustodio/pipefy-mcp-server@latest#subdirectory=packages/mcp",
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

#### Claude Desktop

Config file location:

| OS | Path |
|----|------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

```json
{
  "mcpServers": {
    "pipefy": {
      "command": "uvx",
      "args": [
        "--with",
        "pipefy-sdk @ git+https://github.com/gbrlcustodio/pipefy-mcp-server@latest#subdirectory=packages/sdk",
        "--with",
        "pipefy-auth @ git+https://github.com/gbrlcustodio/pipefy-mcp-server@latest#subdirectory=packages/auth",
        "--from",
        "git+https://github.com/gbrlcustodio/pipefy-mcp-server@latest#subdirectory=packages/mcp",
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

#### Codex

Edit `~/.codex/config.toml`:

```toml
[mcp_servers.pipefy]
command = "uvx"
args = [
  "--with", "pipefy-sdk @ git+https://github.com/gbrlcustodio/pipefy-mcp-server@latest#subdirectory=packages/sdk",
  "--with", "pipefy-auth @ git+https://github.com/gbrlcustodio/pipefy-mcp-server@latest#subdirectory=packages/auth",
  "--from", "git+https://github.com/gbrlcustodio/pipefy-mcp-server@latest#subdirectory=packages/mcp",
  "pipefy-mcp-server",
]
env = { PIPEFY_SERVICE_ACCOUNT_CLIENT_ID = "<CLIENT_ID>", PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET = "<CLIENT_SECRET>" }
```

#### Other MCP clients

Most clients accept a project-root `.mcp.json` with the same shape as the Cursor block above. For `claude mcp add` per-project wiring, the macOS `errSecParam` keychain note, and the local-clone alternative for contributors, see [`packages/mcp/README.md`](packages/mcp/README.md).

### CLI

Ad-hoc:

```sh
uvx \
  --with "pipefy-sdk @ git+https://github.com/gbrlcustodio/pipefy-mcp-server@latest#subdirectory=packages/sdk" \
  --with "pipefy-auth @ git+https://github.com/gbrlcustodio/pipefy-mcp-server@latest#subdirectory=packages/auth" \
  --from "git+https://github.com/gbrlcustodio/pipefy-mcp-server@latest#subdirectory=packages/cli" \
  pipefy-cli --help
```

Permanent install:

```sh
uv tool install \
  --with "pipefy-sdk @ git+https://github.com/gbrlcustodio/pipefy-mcp-server@latest#subdirectory=packages/sdk" \
  --with "pipefy-auth @ git+https://github.com/gbrlcustodio/pipefy-mcp-server@latest#subdirectory=packages/auth" \
  "git+https://github.com/gbrlcustodio/pipefy-mcp-server@latest#subdirectory=packages/cli"
pipefy --install-completion bash    # or zsh, fish
pipefy auth login                   # browser OAuth, session in OS keychain
```

CLI deep-dives (auth precedence, `--token` / `PIPEFY_TOKEN`, parity matrix): [`packages/cli/README.md`](packages/cli/README.md) and [`docs/cli/`](docs/cli/README.md).

### Skill catalog install

```sh
npx skills add gbrlcustodio/pipefy-mcp-server                           # all skills
npx skills add gbrlcustodio/pipefy-mcp-server --skill pipefy-pipes-and-cards
```

Catalog and authoring guide: [`skills/README.md`](skills/README.md).

### Post-1.0 (PyPI preview)

```sh
uvx pipefy-mcp-server
uv tool install pipefy-cli
```

Deprecation and semver (post-1.0): [`docs/DEPRECATION.md`](docs/DEPRECATION.md).

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

The [`skills/`](skills/) directory holds workflow playbooks: prerequisites, tool tables (MCP + CLI), steps, and success criteria. Compatible with any agent that reads Markdown (Cursor, Claude Code, Codex, and others). Distribution is via [`skills.sh`](https://github.com/vercel-labs/skills) (55+ agent targets); install commands are under [Installation](#installation) above.

Full catalog: [`skills/README.md`](skills/README.md). Authoring: [`skills/AGENTS.md`](skills/AGENTS.md). Contributions: [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Documentation

| Document | Description |
|----------|-------------|
| [`docs/README.md`](docs/README.md) | Index by surface (MCP, CLI, SDK). |
| [`docs/config.md`](docs/config.md) | `PIPEFY_*` environment variables, `config.toml` schema and path, precedence chain. |
| [`docs/parity.md`](docs/parity.md) | MCP tool ↔ CLI command matrix. |
| [`docs/MIGRATION.md`](docs/MIGRATION.md) | Notes for existing MCP users. |
| [`AGENTS.md`](AGENTS.md) | Repository guidelines for contributors and agents. |
| [`RELEASE.md`](RELEASE.md) | Versioning and release process. |

---

## Development

Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it, then from the repository root:

```bash
uv sync
[[ -f .env ]] || cp .env.example .env   # first-time setup; then fill in PIPEFY_SERVICE_ACCOUNT_*
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
