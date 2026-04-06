# MCP server for Pipefy

<p align="center">
  <strong>Open-source MCP for Pipefy: 114 tools across pipes, cards, tables, relations, reports, automations, AI agents and observability — built for your IDE, with pagination, introspection and safe deletes.</strong>
</p>

<p align="center">
  🚧 <strong>Alpha Release:</strong> Building in public. <br>
  📢 Share your feedback on GitHub issues or at dev@pipefy.com.
</p>

<p align="center">
  <a href="https://github.com/gbrlcustodio/pipefy-mcp-server/actions"><img src="https://github.com/gbrlcustodio/pipefy-mcp-server/workflows/CI/badge.svg" alt="CI Status" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+" /></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/uv-package%20manager-blueviolet" alt="uv package manager" /></a>
  <a href="https://modelcontextprotocol.io/introduction"><img src="https://img.shields.io/badge/MCP-Server-orange" alt="MCP Server" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License" /></a>
</p>

> **⚠️ Disclaimer:** This is a "Build in public" project primarily aimed at developer workflows. It is **not** the official, supported Pipefy integration for external enterprise clients, but rather a tool to facilitate the development experience for those who use Pipefy for task management.

## Table of contents
<p align="center">
  <a href="#mcp-tools">MCP tools</a> •
  <a href="#getting-started">Getting started</a> •
  <a href="#mcp-clients">MCP clients</a> •
  <a href="#development--testing">Development & Testing</a> •
  <a href="#contributing">Contributing</a>
</p>

---

## MCP tools

**114 tools** across 9 categories. Each tool has a docstring consumed by LLM clients for routing — treat those as the source of truth for arguments.

**Shared conventions (many tools):**
- **Pagination** — List endpoints accept `first` and `after`. Use `pageInfo.hasNextPage` and `pageInfo.endCursor` to fetch the next page.
- **`debug=true`** — Failed calls may include extra detail: GraphQL error codes and a `correlation_id` for support.
- **`extra_input`** — Optional map of extra mutation fields (camelCase keys). Values that overlap the tool’s main parameters are ignored.
- **Destructive deletes** — Two steps by default: the first response is a preview; call again with `confirm=true` to run the delete.
- **Schema introspection** — `introspect_type`, `introspect_query`, `introspect_mutation` reveal live schema shapes; `search_schema` finds types by keyword with optional `kind` filter; `max_depth` on any introspection tool resolves sub-types in a single call.

| Category | Tools | Description | Docs |
|----------|:-----:|-------------|------|
| **Pipes & cards** | 34 | Read, create, update, and delete pipes, phases, fields, labels, cards, field conditions, and card attachment uploads. | [Details](docs/tools/pipes-and-cards.md) |
| **Database tables** | 18 | Tables, records (rows), schema columns (table fields), org-wide table discovery, and table-record attachment uploads. | [Details](docs/tools/database-tables.md) |
| **Relations** | 5 | Link pipes, tables, and cards across workflows. | [Details](docs/tools/relations.md) |
| **Reports** | 16 | Pipe and organization reports: discovery, CRUD, and async exports. | [Details](docs/tools/reports.md) |
| **Automations & AI** | 16 | Traditional automations (rules engine) and AI-powered automations and agents. | [Details](docs/tools/automations-and-ai.md) |
| **Observability** | 10 | AI agent and automation logs, usage stats, credits, job exports, status polling, and CSV fetch for finished exports. | [Details](docs/tools/observability.md) |
| **Members, email & webhooks** | 9 | Pipe membership, card inbox emails, and webhook management. | [Details](docs/tools/members-email-webhooks.md) |
| **Organization** | 1 | Fetch organization details (plan, members, pipes count). | [Details](docs/tools/organization.md) |
| **Introspection** | 5 | Schema discovery, depth-controlled type resolution, and raw GraphQL execution. | [Details](docs/tools/introspection.md) |

---

## Getting Started

### Prerequisites
- Python 3.11+
- A **Pipefy Service Account Token** (Generate in Admin Panel > Service Accounts).

Remember to add the service account to the pipe you want the AI to use.

### Installation
We recommend using `uv` for dependency management. Ensure it's [installed](https://docs.astral.sh/uv/getting-started/installation/#__tabbed_1_1).

```sh
# Clone the repository
git clone https://github.com/gbrlcustodio/pipefy-mcp-server.git
cd pipefy-mcp-server

# Sync dependencies
uv sync

# Optional: copy template and edit (see docs/configuration.md)
cp .env.example .env
```

**Environment variables:** names, placeholders, and how `.env` interacts with Pydantic Settings are documented in **[Configuration](docs/configuration.md)** (keys themselves live only in [`.env.example`](.env.example)).

## MCP clients

Step-by-step JSON samples and CLI examples live in **[MCP client setup](docs/mcp-client-setup.md)**:

| Client | Doc |
|--------|-----|
| **Cursor** | [Cursor](docs/mcp-client-setup.md#cursor) |
| **Claude Desktop** | [Claude Desktop](docs/mcp-client-setup.md#claude-desktop) |
| **Claude Code** | [Claude Code](docs/mcp-client-setup.md#claude-code) |

## Development & Testing

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=src/pipefy_mcp/services/pipefy --cov-report=term-missing

# Integration tests (requires .env with PIPEFY_* OAuth settings)
uv run pytest -m integration -v

# Attachment upload live tests (optional IDs — see tests/tools/test_attachment_tools_live.py)
# uv run pytest tests/tools/test_attachment_tools_live.py -m integration -v
```

### MCP Inspector

```bash
npx @modelcontextprotocol/inspector uv --directory . run pipefy-mcp-server
```

### Code Quality

```bash
# Lint code
uv run ruff check src/

# Format code
uv run ruff format src/
```

## Contributing
We are building this in public and we need your feedback!

- **Field mapping:** If you encounter a complex field type that the Agent doesn't fill correctly, please open an issue.
- **New tools:** What other Pipefy actions would improve your workflow? Feel free to open an issue or a PR explaining what it is and how you would use it.
