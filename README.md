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

**pipefy-labs** — open-source tools for Pipefy developers: an **MCP server** (128 tools for AI agents), a **CLI** (`pipefy` command for humans and scripts), and an **agent skills catalog** (`skills/`). Built in public — [feedback & issues](https://github.com/<owner>/pipefy-labs/issues) or **dev@pipefy.com**

> **Disclaimer:** Community project for developer workflows — not Pipefy's official or supported integration for external enterprise use.

## Table of contents
<p align="center">
  <a href="#install">Install</a> •
  <a href="#whats-in-this-repo">What's in this repo</a> •
  <a href="#mcp-tools">MCP tools</a> •
  <a href="#skills">Skills</a> •
  <a href="#development--testing">Development & Testing</a> •
  <a href="#contributing">Contributing</a>
</p>

---

## Install

### Pre-launch (v0.x, including public betas) — install from git

> **These commands are temporary.** At **v1.0** the canonical install moves to PyPI.

The next **public beta** on this monorepo follows the **`v0.2.0-beta.*`** tag line (first tag: **`v0.2.0-beta.1`**), after the standalone [`v0.1.0-beta.1`](https://github.com/gbrlcustodio/pipefy-mcp-server/releases/tag/v0.1.0-beta.1). Pin installs to that tag when you want the beta snapshot instead of floating `main`:

```sh
uvx --from git+https://github.com/<owner>/pipefy-labs@v0.2.0-beta.1 --refresh pipefy-mcp-server --help
uvx --from git+https://github.com/<owner>/pipefy-labs@v0.2.0-beta.1 --refresh pipefy-cli --version
```

**MCP server** (for Cursor, Claude Desktop, etc.):

```sh
uvx --from git+https://github.com/<owner>/pipefy-labs --refresh pipefy-mcp-server
```

**CLI** (for scripts, shell automation, agent workflows):

```sh
uvx --from git+https://github.com/<owner>/pipefy-labs --refresh pipefy-cli
```

Or install both permanently with `uv tool install`:

```sh
uv tool install "pipefy-mcp-server @ git+https://github.com/<owner>/pipefy-labs"
uv tool install "pipefy-cli @ git+https://github.com/<owner>/pipefy-labs"
```

### Post-v1.0 — install from PyPI

```sh
# MCP server
uvx pipefy-mcp-server

# CLI (install once and use anywhere)
uv tool install pipefy-cli
```

**Setup, env vars, and MCP client config:** see **[docs/setup.md](docs/setup.md)** for first-time install, Pydantic / `.env` precedence, and Cursor / Claude Desktop examples.

**Documentation index** (MCP vs CLI vs SDK): **[docs/README.md](docs/README.md)**.

**Post-1.0 deprecation and semver:** **[docs/DEPRECATION.md](docs/DEPRECATION.md)**.

---

## What's in this repo

A **uv workspace** with three packages and a skills catalog. **`pipefy-sdk`** is the vendor GraphQL client library shared by MCP and CLI (not a generic “shared utils” package).

| Path | Distribution name | Role |
|------|-------------------|------|
| [`packages/sdk/`](packages/sdk/) | `pipefy-sdk` | **Vendor API SDK** — GraphQL transport, services, queries, Pydantic models. Required by MCP and CLI. [README](packages/sdk/README.md) |
| [`packages/mcp/`](packages/mcp/) | `pipefy-mcp-server` | **MCP adapter** — 128 tools for AI agents (Cursor, Claude, etc.). Depends on `pipefy-sdk`. [README](packages/mcp/README.md) |
| [`packages/cli/`](packages/cli/) | `pipefy-cli` | **CLI** — `pipefy` command for humans and scripts. Depends on `pipefy-sdk`. [README](packages/cli/README.md) |
| [`skills/`](skills/) | — | **Agent skills catalog** — Anthropic Skills-format playbooks for common Pipefy workflows. [Browse skills](skills/README.md) |

---

## MCP tools

The server exposes **128 tools**, grouped by domain. Canonical names live in `PIPEFY_TOOL_NAMES` (`packages/mcp/src/pipefy_mcp/tools/registry.py`).

**Documentation for agents:** each tool's description and `Args:` come from its Python docstring — MCP clients show that text to LLMs for routing. Per-area docs below are the authority on parameters and edge cases.

**Cross-cutting behavior** (pagination, IDs, `debug`, `extra_input`, two-step deletes, permissions, error shape) lives in **[`docs/mcp/tools/cross-cutting.md`](docs/mcp/tools/cross-cutting.md)**.

| Category | Tools | Description | Docs |
|----------|:-----:|-------------|------|
| **Pipes & cards** | 37 | Pipes, phases, fields, labels, cards, field conditions, and card-level attachments. | [Details](docs/mcp/tools/pipes-and-cards.md) |
| **Database tables** | 17 | Tables, records, schema columns, and table-record attachment uploads. | [Details](docs/mcp/tools/database-tables.md) |
| **Relations** | 8 | Pipe relations, table relations, card links, list/delete card-level relations. | [Details](docs/mcp/tools/relations.md) |
| **Reports** | 17 | Pipe and organization reports: discovery, CRUD, single read, and async exports. | [Details](docs/mcp/tools/reports.md) |
| **Automations & AI** | 22 | Traditional automations, AI automations, AI agents, and pre-flight validators. | [Details](docs/mcp/tools/automations-and-ai.md) |
| **Observability** | 10 | Agent and automation logs, usage stats, credits, job exports, status polling. | [Details](docs/mcp/tools/observability.md) |
| **Members, email & webhooks** | 11 | Pipe membership, card inbox emails, webhooks (list/update/create/delete). | [Details](docs/mcp/tools/members-email-webhooks.md) |
| **Organization** | 1 | Fetch organization details (plan, members, pipes count). | [Details](docs/mcp/tools/organization.md) |
| **Introspection** | 5 | Schema discovery, depth-controlled type resolution, and raw GraphQL execution. | [Details](docs/mcp/tools/introspection.md) |

---

## Skills

`skills/` contains **Anthropic Skills-format** playbooks: one Markdown file per workflow describing tools needed, sequence, and success criteria. Any agent that reads files (Claude Code, Cursor, Codex) can use them.

```sh
# Show all bundled skills
pipefy skills list

# Print a skill to stdout (pipe to clipboard, less, or agent context)
pipefy skills show pipes-and-cards
```

Browse the full catalog in [`skills/README.md`](skills/README.md). Contribution guide: [`skills/CONTRIBUTING.md`](skills/CONTRIBUTING.md).

---

## Development & Testing

### Running tests

```bash
uv run pytest                                                   # all tests
uv run pytest -m "not integration"                              # unit tests only
uv run pytest -m integration -v                                 # live API tests
uv run pytest --cov=packages/sdk/src/pipefy_sdk --cov-report=term-missing
```

### Code quality

```bash
uv run ruff check .      # lint all packages
uv run ruff format .     # format all packages
```

### MCP Inspector

```bash
npx @modelcontextprotocol/inspector uv --directory . run pipefy-mcp-server
```

### Adding a new MCP tool

1. Implement in `packages/mcp/src/pipefy_mcp/tools/` and call its `*Tools.register(...)` from `ToolRegistry.register_tools()`.
2. Add the **exact tool name** to `PIPEFY_TOOL_NAMES` in `packages/mcp/src/pipefy_mcp/tools/registry.py`.
3. Following the parity rule, also expose a matching CLI command in `packages/cli/src/pipefy_cli/commands/` (or record a deferral in `docs/parity.md`).

---

## Contributing

We are building this in public and we need your feedback!

- **Field mapping:** If you encounter a complex field type that the agent doesn't fill correctly, please open an issue.
- **New tools:** What other Pipefy actions would improve your workflow? Open an issue or a PR.
- **New skills:** Markdown-only — no Python or test infrastructure required. See [`skills/CONTRIBUTING.md`](skills/CONTRIBUTING.md).
- **Existing MCP users:** see [`docs/MIGRATION.md`](docs/MIGRATION.md) — your config keeps working.
