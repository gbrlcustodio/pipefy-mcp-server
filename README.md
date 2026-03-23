# MCP server for Pipefy

<p align="center">
  <strong>Pipefy MCP is an open-source MCP server that lets your IDE safely create cards, update field information, and use any Pipefy resource — all with built-in safety controls.</strong>
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
  <a href="#usage-with-cursor">Usage with Cursor</a> •
  <a href="#development--testing">Development & Testing</a> •
  <a href="#contributing">Contributing</a>
</p>

---

## MCP tools

**108 tools** across 8 categories. Each tool has a docstring consumed by LLM clients for routing — treat those as the source of truth for arguments.

**Common patterns across all tools:**
- **Pagination** — list tools support `first` / `after`. Read `pageInfo.hasNextPage` and `pageInfo.endCursor` from the response.
- **`debug=true`** — on errors, appends GraphQL codes and `correlation_id` to the error message.
- **`extra_input`** — merges extra API keys (camelCase) into the mutation input. Keys that duplicate primary arguments are ignored.
- **Destructive deletes** — two-step: first call returns a preview, second call with `confirm=true` executes the delete.
- **`introspect_type`** — discover allowed field types, enum values, and input shapes from the live API schema.

| Category | Tools | Description | Docs |
|----------|:-----:|-------------|------|
| **Pipes & cards** | 33 | Read, create, update, and delete pipes, phases, fields, labels, cards, and field conditions. | [Details](docs/tools/pipes-and-cards.md) |
| **Database tables** | 15 | Tables, records (rows), and schema columns (table fields). | [Details](docs/tools/database-tables.md) |
| **Relations** | 6 | Link pipes, tables, and cards across workflows. | [Details](docs/tools/relations.md) |
| **Reports** | 16 | Pipe and organization reports: discovery, CRUD, and async exports. | [Details](docs/tools/reports.md) |
| **Automations & AI** | 15 | Traditional automations (rules engine) and AI-powered automations and agents. | [Details](docs/tools/automations-and-ai.md) |
| **Observability** | 10 | AI agent and automation logs, usage stats, credits, job exports, status polling, and CSV fetch for finished exports. | [Details](docs/tools/observability.md) |
| **Members, email & webhooks** | 9 | Pipe membership, card inbox emails, and webhook management. | [Details](docs/tools/members-email-webhooks.md) |
| **Introspection** | 4 | Schema discovery and raw GraphQL execution. | [Details](docs/tools/introspection.md) |

---

## Getting Started

### Prerequisites
- Python 3.11+
- A **Pipefy Service Account Token** (Generate in Admin Panel > Service Accounts).
- Remember to add the service account to the pipe you want the AI to use.

### Installation
We recommend using `uv` for dependency management. Ensure it's [installed](https://docs.astral.sh/uv/getting-started/installation/#__tabbed_1_1).

```sh
# Clone the repository
git clone https://github.com/gbrlcustodio/pipefy-mcp-server.git
cd pipefy-mcp-server

# Sync dependencies
uv sync
```

## Usage with Cursor
To use this with Cursor, you need to register it as an MCP server in your settings.

1. Open Cursor.
1. Navigate to Cursor Settings > Features > MCP Servers.
1. Click + Add New MCP Server.
1. Fill in the details as shown in the configuration block below.

```json
{
    "mcpServers": {
        "pipefy": {
            "cwd": "/absolute/path/to/pipefy-mcp-server",
            "command": "uv",
            "args": [
                "run",
                "--directory",
                ".",
                "pipefy-mcp-server"
            ],
            "env": {
                "PIPEFY_GRAPHQL_URL": "https://app.pipefy.com/graphql",
                "PIPEFY_OAUTH_URL": "https://app.pipefy.com/oauth/token",
                "PIPEFY_OAUTH_CLIENT": "<SERVICE_ACCOUNT_CLIENT_ID>",
                "PIPEFY_OAUTH_SECRET": "<SERVICE_ACCOUNT_CLIENT_SECRET>"
            }
        }
    }
}
```

## Development & Testing

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=src/pipefy_mcp/services/pipefy --cov-report=term-missing

# Integration tests (requires .env with PIPEFY_* OAuth settings)
uv run pytest -m integration -v
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
