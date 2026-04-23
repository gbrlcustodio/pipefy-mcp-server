# MCP server for Pipefy

<p align="center">
  <strong>Open-source MCP for Pipefy: 128 tools across pipes, cards, tables, relations, reports, automations, AI agents and observability — built for your IDE, with pagination, introspection and safe deletes.</strong>
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

The server exposes **128 tools**, grouped below into **nine** surface areas. Canonical names live in `PIPEFY_TOOL_NAMES` (`src/pipefy_mcp/tools/registry.py`).

**Documentation for agents:** each tool’s description and `Args:` come from its Python docstring—MCP clients show that text to LLMs for routing. Use the docstrings (and the per-area docs linked in the table) as the authority on parameters and edge cases.

**Cross-cutting behavior**

- **Pagination** — List-style tools accept `first` and `after`. Continue with `pageInfo.endCursor` while `pageInfo.hasNextPage` is true.
- **IDs** — Pipefy GraphQL uses string IDs. Pass IDs as strings (e.g. `"301234"`). Some parameters also accept JSON integers; the server normalizes to string before calling the API. Success payloads return string IDs. Empty, zero, or otherwise invalid IDs fail validation before any network call. More detail: [Pipefy IDs and type safety](docs/tools/pipes-and-cards.md#pipefy-ids-type-safety).
- **`debug=true`** — On failures, error text may include GraphQL codes and a `correlation_id` for support.
- **`extra_input`** — Optional map of extra mutation fields (camelCase keys). Keys that duplicate the tool’s primary parameters are ignored.
- **Destructive operations** — Deletes use a two-step contract: call with `confirm=false` (default) for a preview, then `confirm=true` only after explicit approval to execute.
- **Automatic `PERMISSION_DENIED` enrichment** — On cross-pipe operations (relations, AI agents), errors carrying `extensions.code = PERMISSION_DENIED` are enriched with a membership hint pointing to `invite_members` when the service account is missing from the target pipe. Runs automatically (no `debug=true` required); implementation in [`enrich_permission_denied_error`](src/pipefy_mcp/tools/graphql_error_helpers.py).
- **Service Account Protection** — When the optional [`PIPEFY_SERVICE_ACCOUNT_IDS`](.env.example) env var is set, the server guards `remove_member_from_pipe` and `set_role` against locking the service account out of its own pipes. See [Service Account Protection](docs/tools/members-email-webhooks.md#service-account-protection) for the full contract.
- **Pre-flight validation for AI features** — Before creating/updating AI automations or AI agents, call [`validate_ai_automation_prompt`](docs/tools/automations-and-ai.md#ai-automations) and [`validate_ai_agent_behaviors`](docs/tools/automations-and-ai.md#ai-agent-read--delete) to catch prompt/field/event errors and membership gaps without round-tripping the write mutation.
- **Introspection** — `introspect_type`, `introspect_query`, and `introspect_mutation` expose live schema; `search_schema` lists types by keyword (optional `kind` filter). Use `max_depth` where supported to expand nested types in one round trip. Set `include_parsed=true` to also receive a `data` dict for programmatic access.
- **Error payloads** — When a GraphQL exception carries a structured `errors` list, error payloads now return only the extracted `message` strings (without the noisy `str(exc)` wrapper that previously included `locations` / `extensions`). The raw string is used as a fallback only when no structured messages can be extracted.

| Category | Tools | Description | Docs |
|----------|:-----:|-------------|------|
| **Pipes & cards** | 37 | Pipes, phases, fields, labels, cards, field conditions, and card-level attachments—read/write/delete as documented per tool (card-to-card relation list/delete live under **Relations**). | [Details](docs/tools/pipes-and-cards.md) |
| **Database tables** | 17 | Tables, records (rows), schema columns (table fields), org-wide table discovery, and table-record attachment uploads. | [Details](docs/tools/database-tables.md) |
| **Relations** | 8 | Pipe relations, table relations by ID, card links, list/delete card-level relations. | [Details](docs/tools/relations.md) |
| **Reports** | 17 | Pipe and organization reports: discovery, CRUD, single pipe report read, and async exports. | [Details](docs/tools/reports.md) |
| **Automations & AI** | 22 | Traditional automations (rules engine), AI automations, and AI agents — including pre-flight validation (`validate_ai_automation_prompt`, `validate_ai_agent_behaviors`) to catch prompt/field/event errors before write. | [Details](docs/tools/automations-and-ai.md) |
| **Observability** | 10 | AI agent and automation logs, usage stats, credits, job exports, status polling, and CSV fetch for finished exports. | [Details](docs/tools/observability.md) |
| **Members, email & webhooks** | 11 | Pipe membership, card inbox emails, webhooks (list/update/create/delete), and transactional email sends. | [Details](docs/tools/members-email-webhooks.md) |
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

# Optional: copy template and edit (full guide: docs/setup.md)
cp .env.example .env
```

**Setup, env vars, and MCP client JSON:** use **[Setup](docs/setup.md)** — single doc for first-time install, Pydantic / `.env` precedence, and Cursor / Claude examples (keys in [`.env.example`](.env.example)). Optional: `./bootstrap.sh` runs `uv sync` and creates `.env` from `.env.example` if missing.

### Why these dependencies?

The runtime stack in [`pyproject.toml`](pyproject.toml) is small on purpose. For a longer rationale (code references and security notes), see **[Dependencies](docs/dependencies.md)**. Summary:

| Package | Role in this server |
|--------|---------------------|
| **httpx** | Async HTTP client used by `gql` for GraphQL (`HTTPXAsyncTransport`), Pipefy’s internal GraphQL API, presigned S3 uploads/downloads for attachments, and downloading signed export URLs (automation job / observability flows). |
| **httpx-auth** | `OAuth2ClientCredentials` for service-account token acquisition and refresh; shared across GraphQL clients and direct `httpx` calls that need the same Pipefy OAuth settings. |
| **openpyxl** | Reads `.xlsx` export files (e.g. automation job exports) and converts the first worksheet to CSV text for MCP responses — see `observability_export_csv`. |

## MCP clients

Step-by-step JSON samples and CLI examples are in **[Setup → MCP client setup](docs/setup.md#mcp-client-setup)**.

| Client | Section |
|--------|---------|
| **Cursor** | [Cursor](docs/setup.md#cursor) |
| **Claude Desktop** | [Claude Desktop](docs/setup.md#claude-desktop) |
| **Claude Code** | [Claude Code](docs/setup.md#claude-code) |

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
