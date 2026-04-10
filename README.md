# MCP server for Pipefy

<p align="center">
  <strong>Open-source MCP for Pipefy: 115 tools across pipes, cards, tables, relations, reports, automations, AI agents and observability — built for your IDE, with pagination, introspection and safe deletes.</strong>
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
  <a href="#why-these-dependencies">Why these dependencies?</a> •
  <a href="#mcp-clients">MCP clients</a> •
  <a href="#development--testing">Development & Testing</a> •
  <a href="#contributing">Contributing</a>
</p>

---

## MCP tools

**115 tools** across 9 categories. Each tool has a docstring consumed by LLM clients for routing — treat those as the source of truth for arguments.

**Shared conventions (many tools):**
- **Pagination** — List endpoints accept `first` and `after`. Use `pageInfo.hasNextPage` and `pageInfo.endCursor` to fetch the next page.
- **Pipefy IDs** — GraphQL treats IDs as **strings**. Tool parameters accept **string IDs** (recommended: `"301234"`). Clients that send unquoted JSON numbers may pass integers for some parameters; the server coerces them to strings before calling the API. Responses and success payloads return IDs as **strings**. Invalid IDs (e.g. empty, zero, or non-coercible values) are rejected before the network call. See [Pipes & cards — IDs](docs/tools/pipes-and-cards.md#pipefy-ids-type-safety) for `delete_card` and card/pipe parameters.
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
| **Automations & AI** | 17 | Traditional automations (rules engine) and AI-powered automations and agents. | [Details](docs/tools/automations-and-ai.md) |
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

### Why these dependencies?

The runtime stack in [`pyproject.toml`](pyproject.toml) is small on purpose. For a longer rationale (code references and security notes), see **[Dependencies](docs/dependencies.md)**. Summary:

| Package | Role in this server |
|--------|---------------------|
| **httpx** | Async HTTP client used by `gql` for GraphQL (`HTTPXAsyncTransport`), Pipefy’s internal GraphQL API, presigned S3 uploads/downloads for attachments, and downloading signed export URLs (automation job / observability flows). |
| **httpx-auth** | `OAuth2ClientCredentials` for service-account token acquisition and refresh; shared across GraphQL clients and direct `httpx` calls that need the same Pipefy OAuth settings. |
| **openpyxl** | Reads `.xlsx` export files (e.g. automation job exports) and converts the first worksheet to CSV text for MCP responses — see `observability_export_csv`. |

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

### Adding or renaming an MCP tool

1. Implement the tool in the appropriate module under `src/pipefy_mcp/tools/` and call its `*Tools.register(...)` from `ToolRegistry.register_tools()` in [`src/pipefy_mcp/tools/registry.py`](src/pipefy_mcp/tools/registry.py) if it is not already wired.
2. Add the **exact tool name** (as exposed to MCP clients) to **`PIPEFY_TOOL_NAMES`** in the same file. The server uses that set for collision checks at startup and for cleanup after a failed registration; `tests/test_server.py` also asserts the live tool list matches this set.

### Manual smoke test (Cursor MCP)

After meaningful changes to **`server.py`**, the **lifespan**, or **tool registration** (including `PIPEFY_TOOL_NAMES`), validate the real stack—not only unit tests:

1. Add or enable this server in **Cursor MCP settings** and run the server, for example: `uv run pipefy-mcp-server` — this starts the MCP server defined in this repo so Cursor can connect to it.
2. From the chat or MCP tools panel, confirm tools load (e.g. list tools / invoke a simple read-only tool you care about).

Inspector (`npx @modelcontextprotocol/inspector …`) remains useful for protocol debugging; Cursor MCP is the preferred sign-off for “tools work as we use them.”

## Contributing
We are building this in public and we need your feedback!

- **Field mapping:** If you encounter a complex field type that the Agent doesn't fill correctly, please open an issue.
- **New tools:** What other Pipefy actions would improve your workflow? Feel free to open an issue or a PR explaining what it is and how you would use it.
