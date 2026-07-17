<div align="center">
  <img
    src="docs/images/pipefy-developers-banner.png"
    alt="Pipefy Developers — Where developers orchestrate intelligence"
    width="100%"
  />
</div>

<p align="center">
  <a href="https://github.com/pipefy/ai-toolkit/actions/workflows/ci.yml"><img src="https://github.com/pipefy/ai-toolkit/actions/workflows/ci.yml/badge.svg" alt="CI Status" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+" /></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/uv-package%20manager-blueviolet" alt="uv package manager" /></a>
  <a href="https://modelcontextprotocol.io/introduction"><img src="https://img.shields.io/badge/MCP-Server-orange" alt="MCP Server" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License" /></a>
</p>

# Pipefy AI Toolkit

Open-source toolkit for **Pipefy** developers: a Model Context Protocol (MCP) server for AI agents, a **`pipefy`** CLI for terminals and automation, a shared GraphQL SDK, and a catalog of agent skill playbooks.

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
| **MCP server** | `pipefy-mcp-server` | Exposes **168** tools to MCP clients (Cursor, Claude Desktop, Claude Code, and others). |
| **CLI** | `pipefy-cli` | Terminal commands aligned with MCP capabilities; see [`docs/parity.md`](docs/parity.md). |
| **SDK** | `pipefy` | Vendor GraphQL client, services, and models shared by MCP and CLI. |
| **Skills** | [`skills/`](skills/) | Markdown playbooks (Anthropic Skills format) for common Pipefy workflows. |

Feedback and issues: [GitHub Issues](https://github.com/pipefy/ai-toolkit/issues) · **dev@pipefy.com**

---

## Installation

> Pre-1.0 ships pre-release builds to PyPI on every tag; `uvx` and `uv tool install` resolve them. A stable PyPI release becomes the default at **v1.0**. The current pre-release line is **`v0.3.0-alpha.*`** (first tag: [`v0.3.0-alpha.1`](https://github.com/pipefy/ai-toolkit/releases/tag/v0.3.0-alpha.1)). Two install paths: the **Quick install** script below (resolves the latest GitHub Release at runtime and runs `uv tool install` for you), or **Claude Code** via the plugin marketplace.
>
> The CLI snippets below install `pipefy-cli` from PyPI, which resolves `pipefy` and `pipefy-auth` transitively (no explicit `--with` needed). While the toolkit ships only pre-release versions (the 0.x line), `uv` resolves the latest pre-release automatically; to pin a specific one, use `pipefy-cli==X.Y.Z` (PEP 440 form, e.g. `pipefy-cli==0.3.0a1`). Do not pass a global `--prerelease allow`: it also lets transitive dependencies jump to their own pre-releases, which can pull a broken build.

Two auth paths:

- **Human OAuth (interactive)**: `pipefy auth login` runs the browser flow and stores a session in your OS keychain. Works anywhere the `pipefy` CLI is on PATH (`uv tool install` once, any client can invoke it). Claude Code additionally exposes it as the `/pipefy:pipefy-login` slash command via the plugin marketplace. Pipe membership is whatever the signed-in user already has.
- **Service account (unattended / CI)**: provision a Service Account in [Pipefy Admin](https://app.pipefy.com/) (Admin → Service Accounts) and add that account to every pipe the tools should touch. Wire `PIPEFY_SERVICE_ACCOUNT_CLIENT_ID` and `PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET` into the client config below.

Full env-var reference and `config.toml` precedence: [`docs/config.md`](docs/config.md).

### Quick install (recommended)

One command installs the CLI + MCP server, optionally adds skills, and registers the MCP server in your client config:

```sh
curl -fsSL https://raw.githubusercontent.com/pipefy/ai-toolkit/main/install.sh \
  | sh -s -- --client cursor
```

Replace `--client cursor` with one of: `claude-code`, `claude-desktop`, `codex`, or `none` (prints the snippet to paste). Useful flags:

- `--yes` skip all confirmation prompts.
- `--no-skills` skip the `npx skills add` step.
- `--version vX.Y.Z` pin a specific [GitHub Release](https://github.com/pipefy/ai-toolkit/releases) tag (default: most recent prerelease or release).
- `--dry-run` print every command without executing.
- `--allow-root` opt-in for root execution (refused by default).

After install, run `pipefy auth login` to authenticate (`--device` on headless systems). The installer puts `pipefy-mcp-server` on PATH, so each client's config collapses to `{"command": "pipefy-mcp-server"}`.

### Claude Code

```text
/plugin marketplace add pipefy/ai-toolkit
/plugin install pipefy
/pipefy:install
/pipefy:pipefy-login
```

`/plugin install pipefy` registers the MCP server and the `/pipefy:install` + `/pipefy:pipefy-login` slash commands. `/pipefy:install` runs `uv tool install` once to put `pipefy` on PATH (idempotent). `/pipefy:pipefy-login` runs the OAuth browser flow. For hand-wired setups (paste-into-config blocks per client, the macOS `errSecParam` keychain note, the local-clone alternative for contributors), see [`packages/mcp/README.md`](packages/mcp/README.md).

### CLI

Ad-hoc:

```sh
uvx --from pipefy-cli pipefy --help
```

Permanent install:

```sh
uv tool install pipefy-cli
pipefy --install-completion bash    # or zsh, fish
pipefy auth login                   # browser OAuth, session in OS keychain
```

CLI deep-dives (auth precedence, `--token` / `PIPEFY_TOKEN`, parity matrix): [`packages/cli/README.md`](packages/cli/README.md) and [`docs/cli/`](docs/cli/README.md).

### Skill catalog install

```sh
npx skills add pipefy/ai-toolkit                           # all skills
npx skills add pipefy/ai-toolkit --skill pipefy-pipes-and-cards
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

`uv` workspace with three Python packages and a skills catalog. **`pipefy`** is the vendor GraphQL layer; MCP and CLI depend on it and do not import each other.

| Path | Distribution | Role |
|------|--------------|------|
| [`packages/sdk/`](packages/sdk/) | `pipefy` | GraphQL transport, services, queries, Pydantic models. [Package README](packages/sdk/README.md) |
| [`packages/mcp/`](packages/mcp/) | `pipefy-mcp-server` | MCP tool registration and server lifecycle. [Package README](packages/mcp/README.md) |
| [`packages/cli/`](packages/cli/) | `pipefy-cli` | Typer CLI (`pipefy` command). [Package README](packages/cli/README.md) |
| [`skills/`](skills/) | — | Agent skill playbooks. [Catalog](skills/README.md) |

---

## MCP server

The server registers **168 tools** across thirteen domains. Canonical names: `PIPEFY_TOOL_NAMES` in [`packages/mcp/src/pipefy_mcp/tools/registry.py`](packages/mcp/src/pipefy_mcp/tools/registry.py).

Tool descriptions and `Args:` blocks come from Python docstrings (what MCP clients show to models). Per-area reference docs cover parameters, edge cases, and cross-cutting behavior.

**Shared conventions** (pagination, IDs, permissions, error shape): [`docs/mcp/tools/cross-cutting.md`](docs/mcp/tools/cross-cutting.md).

| Domain | Tools | Summary | Reference |
|--------|:-----:|---------|-----------|
| **Pipes & cards** | 40 | Pipes, phases, fields, labels, cards, field conditions, attachments. Phase inventory (`get_phase_cards`, `get_phase_cards_count`), move discovery (`get_phase_allowed_move_targets`), and `create_card(phase_id=…)` reduce raw GraphQL for agent seeding. | [docs](docs/mcp/tools/pipes-and-cards.md) |
| **Database tables** | 17 | Tables, records, schema, table-record attachments. | [docs](docs/mcp/tools/database-tables.md) |
| **Relations** | 8 | Pipe and card relations. | [docs](docs/mcp/tools/relations.md) |
| **Reports** | 17 | Pipe and organization reports, async exports. | [docs](docs/mcp/tools/reports.md) |
| **Automations & AI** | 23 | Automations, AI automations, AI agents, validators. | [docs](docs/mcp/tools/automations-and-ai.md) |
| **LLM providers** | 5 | Discovery reads for the organization's LLM providers (custom + Pipefy-managed), vendor model lists, owner defaults, dependencies, and a read-access probe. | [docs](docs/mcp/tools/llm-providers.md) |
| **Knowledge bases** | 6 | Pipe-scoped AI knowledge bases: list all items, plain text CRUD, and a read-access probe. Attach sources to agents/behaviors via `dataSourceIds`. | [docs](docs/mcp/tools/knowledge-bases.md) |
| **iPaaS** | 4 | Lazy discovery, invocation, and app-connection setup for a pipe's iPaaS (Advanced Automations) workspace (`get_ipaas_tools`, `call_ipaas_tool`, plus the connection meta-tools). | [docs](docs/mcp/tools/ipaas.md) |
| **Observability** | 11 | Logs, usage, credits, execution metrics, job exports. | [docs](docs/mcp/tools/observability.md) |
| **Members, email & webhooks** | 11 | Membership, inbox email, webhooks. | [docs](docs/mcp/tools/members-email-webhooks.md) |
| **Organization** | 1 | Organization metadata. | [docs](docs/mcp/tools/organization.md) |
| **Portals** | 20 | Portal read/CRUD, pages, elements, sub-portals (publish/unpublish). | [docs](docs/mcp/tools/portal.md) |
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

**Card & phase agent ergonomics:** use [`skills/pipes-and-cards/pipefy-pipes-and-cards/SKILL.md`](skills/pipes-and-cards/pipefy-pipes-and-cards/SKILL.md) (workflow *Seed pipe across phases*; prefer dedicated tools over `execute_graphql`).

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

### Test the Claude Code plugin from a local checkout

The [Claude Code install](#claude-code) adds the marketplace from the `pipefy/ai-toolkit` GitHub repo, which tracks `main`. To run **your local branch** (e.g. `dev`) as the plugin instead, point the marketplace at your clone:

```text
/plugin marketplace add /absolute/path/to/ai-toolkit
/plugin install pipefy@pipefy
```

Whatever is checked out in that clone — any branch — is what loads. Use the `plugin@marketplace` form (`pipefy@pipefy`) since the marketplace and the plugin share the name `pipefy`. After editing plugin files (skills, commands), run `/reload-plugins` to pick up changes without restarting.

> **Already installed the GitHub version?** A marketplace named `pipefy` can be registered only once, and a marketplace declared in `~/.claude/settings.json` under `extraKnownMarketplaces` is locked — `/plugin marketplace add` becomes a no-op (`already on disk — declared in user settings`) and keeps pointing at GitHub. Run `/plugin marketplace remove pipefy` first (or delete that `extraKnownMarketplaces` entry), **then** add the local path.

---

## Contributing

Contributions are welcome via issues and pull requests.

| Area | How to contribute |
|------|-------------------|
| **Skills** | Markdown only — see [`CONTRIBUTING.md`](CONTRIBUTING.md). |
| **MCP / CLI / SDK** | Follow [`AGENTS.md`](AGENTS.md) and [`docs/parity.md`](docs/parity.md). |
| **Field mapping gaps** | Open an issue with the field type and expected behavior. |
| **Existing MCP setups** | [`docs/MIGRATION.md`](docs/MIGRATION.md) — configuration remains compatible. |
