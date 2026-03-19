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
  <a href="#feature-overview">Feature overview</a> •
  <a href="#mcp-tools-at-a-glance">MCP tools at a glance</a> •
  <a href="#getting-started">Getting started</a> •
  <a href="#usage-with-cursor">Usage with Cursor</a> •
  <a href="#development--testing">Development & Testing</a> •
  <a href="#contributing">Contributing</a>
</p>

## Feature Overview

This server exposes Pipefy operations as **MCP tools** for LLMs (e.g. in Cursor). The codebase uses a facade over domain services (pipes, cards, pipe configuration, **database tables**, **pipe/table relations and card links**, schema introspection), with GraphQL documents in dedicated modules.

**Discoverability:** Each tool has a docstring consumed by clients for routing and parameters—treat those as the source of truth for arguments. This README summarizes **what exists** and **cross-cutting behavior** (pagination, destructive flows, introspection); it does not duplicate every parameter.

---

## MCP tools at a glance

### Reads & search

| Area | Tools |
|------|--------|
| **Pipe** | `get_pipe`, `get_start_form_fields`, `get_phase_fields`, `get_pipe_members`, `search_pipes` |
| **Cards** | `get_cards`, `get_card`, `find_cards` — use `include_fields` when you need custom field name/value on each card. |
| **Database tables** | `get_table`, `get_tables`, `get_table_records`, `get_table_record`, `find_records` |
| **Relations** | `get_pipe_relations`, `get_table_relations` |

### Pipe building (structure & labels)

Create and update pipes, phases, phase fields, and labels. **Field types** are not validated locally—use **`introspect_type`** (e.g. on `CreatePhaseFieldInput`) for allowed values.

Successful mutations return a **structured** `result` (GraphQL payload). Most write tools support optional **`debug=true`** on errors (GraphQL codes + `correlation_id`). **`extra_input`** merges extra API keys; keys that would duplicate primary arguments are ignored (same pattern as table-field tools).

| Group | Tools | Notes |
|-------|--------|--------|
| Pipe | `create_pipe`, `update_pipe`, `delete_pipe`, `clone_pipe` | **`delete_pipe`**: two-step — preview first, then `confirm=true` after user approval. |
| Phase | `create_phase`, `update_phase`, `delete_phase` | Destructive deletes: confirm with the user. |
| Phase field | `create_phase_field`, `update_phase_field`, `delete_phase_field` | `field_type` maps to API `type`; `field_id` may be a slug or numeric ID. |
| Label | `create_label`, `update_label`, `delete_label` | **`color`** must be a **hex** string (e.g. `#FF0000`), not a name. |

### Cards (lifecycle & comments)

| Tool | Role |
|------|------|
| `create_card` | Create a card; may use **elicitation** to ask the user for required fields mid-call. |
| `add_card_comment`, `update_comment`, `delete_comment` | Comments (`text` length limits enforced). |
| `move_card_to_phase` | Move card to another phase. |
| `update_card_field` | Single-field update (`updateCardField`). |
| `update_card` | Metadata (`title`, assignees, labels, due date) **and/or** multiple custom fields via `field_updates`. |
| `delete_card` | **Two-step**: default preview; `confirm=true` after explicit user confirmation. |

**Choosing card updates:** `update_card_field` = one field, full replacement. `update_card` + `field_updates` = several custom fields at once. `update_card` with attribute args = metadata (combinable with `field_updates`).

<details>
<summary><strong>Optional:</strong> sequence diagram for <code>create_card</code> + elicitation</summary>

```mermaid
sequenceDiagram
    participant U as User
    participant A as Agent
    participant S as MCP Server
    participant P as Pipefy API

    U->>A: "Create a new card in pipe 123"
    A->>S: create_card(pipe_id=123)
    S->>P: Get required fields for pipe 123
    S-->>A: Elicit(fields=["title", "due_date"])
    A-->>U: I need more information: Title, Due Date
    U-->>A: "Fix bug in login", "2025-12-31"
    A->>S: create_card(pipe_id=123, title="Fix bug in login", due_date="2025-12-31")
    S->>P: mutation createCard(...)
    P-->>S: {"data": {"createCard": ...}}
    S-->>A: {"success": true, "card_id": 456}
```

</details>

### Database tables (reference data)

**15 tools** for org **Database Tables**: metadata, rows (records), and **schema columns** (table fields). Same conventions as pipe building: **`introspect_type`** on inputs such as `CreateTableFieldInput` / `UpdateTableFieldInput`, **`debug=true`** on mutations, **`extra_input`** where the tool exposes it.

| Domain | Tools |
|--------|--------|
| **Read** | `get_table`, `get_tables`, `get_table_records`, `get_table_record`, `find_records` |
| **Table CRUD** | `create_table`, `update_table`, `delete_table` — **`delete_table`** uses preview + `confirm=true` (like `delete_pipe`). |
| **Record CRUD** | `create_table_record`, `update_table_record`, `delete_table_record`, `set_table_record_field_value` |
| **Field CRUD** | `create_table_field`, `update_table_field`, `delete_table_field` — schema columns; **`delete_table_field`** is destructive (confirm with the user). |

**Pagination:** `get_table_records` and `find_records` support **`first`** / **`after`**. Read `pageInfo.hasNextPage` and `pageInfo.endCursor` from the tool response and pass `after=endCursor` for the next page (default page size for listing records is 50; caps apply—see tool docstrings).

### Connections & relation tools

**Six tools** link processes and cards across workflows:

- **Pipe relations** define parent/child structure between pipes (who connects to whom, constraints, auto-fill). Use **`get_pipe_relations`** on a pipe to list relation IDs and metadata.
- **Card relations** connect individual cards through an existing pipe relation: pass **`source_id`** = that pipe relation’s ID (from `get_pipe_relations`). Default **`sourceType`** is `PipeRelation`; use **`extra_input`** (e.g. `sourceType: Field`) when the API requires a field-based link—see **`introspect_type`** on `CreateCardRelationInput`.
- **Table relations** in GraphQL are loaded by **table-relation ID**, not by database table ID: **`get_table_relations`** takes a non-empty list of those IDs (root `table_relations` query).

| Tool | Read-only | Role |
|------|-----------|------|
| `get_pipe_relations` | Yes | Lists parent/child pipe relations for a pipe. |
| `get_table_relations` | Yes | Batch-loads table relations by **relation** ID list. |
| `create_pipe_relation` | No | Creates a parent–child relation between two pipes; optional **`extra_input`** (camelCase) for `CreatePipeRelationInput`. |
| `update_pipe_relation` | No | Updates relation config; **`name`** required; optional **`extra_input`** for other `UpdatePipeRelationInput` keys. |
| `delete_pipe_relation` | No | Permanently deletes a pipe relation (**`destructiveHint=True`** — confirm with the user first). |
| `create_card_relation` | No | Links a child card to a parent card via **`source_id`** (pipe relation ID); optional **`extra_input`** for `CreateCardRelationInput`. Mutations support **`debug=true`** on errors like other write tools. |

### AI automations & agents

| Tool | Purpose |
|------|---------|
| `create_ai_automation` | Prompt-driven automation writing to one or more card fields (AI must be enabled on the pipe in Pipefy). |
| `update_ai_automation` | Change name, `active`, prompt, `field_ids`, or `condition`. |
| `create_ai_agent` | Create an agent on a pipe; **`repo_uuid`** is the pipe UUID from `get_pipe`, not the URL numeric id alone. |
| `update_ai_agent` | Replaces full agent config; send the **complete** `behaviors` list (1–5). |
| `toggle_ai_agent_status` | Enable/disable without resending configuration. |

### Introspection & raw GraphQL

When the schema shifts or no dedicated tool exists: **discovery** tools plus a **last-resort** executor (same OAuth client as everything else).

| Tool | Read-only hint | Purpose |
|------|----------------|--------|
| `introspect_type` | Yes | Type shape: `fields`, `inputFields`, `enumValues`. |
| `introspect_mutation` | Yes | Mutation arguments and return type. |
| `search_schema` | Yes | Keyword search on type names/descriptions. |
| `execute_graphql` | **No** | Arbitrary document (syntax-checked). **Prefer dedicated tools.** |

Responses: `success` / `result` or `error`; transport GraphQL errors are surfaced clearly.

## Getting Started

### Prerequisites
Installing the server requires the following on your system:
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
```

### Inspecting locally developed servers
To inspect servers locally developed or downloaded as a repository, the most common way is using the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector uv --directory . run pipefy-mcp-server
```

This is the **same entrypoint** (`pipefy-mcp-server` → full FastMCP app, lifespan, and all tools). Use it to call any registered tool with the same JSON arguments the IDE will send (pipe building, cards, **database tables**, introspection, etc.).

**Quick Inspector checks**

- **`create_label`**: `color` must be a **hex string** (e.g. `#FF0000`) — see `introspect_type` on `CreateLabelInput`.
- **`delete_pipe`** / **`delete_table`**: first call without `confirm` returns a **preview**; call again with `confirm=true` after user approval to delete.

### Integration tests (full MCP stack)

Automated tests that call tools through **`pipefy_mcp.server.mcp`** (identical MCP path to production) are in `tests/tools/test_pipe_config_tools_live.py`. They require a `.env` with valid `PIPEFY_*` OAuth settings.

```bash
# Read-only + any test that only needs creds (e.g. introspect_type)
uv run pytest tests/tools/test_pipe_config_tools_live.py -m integration -v

# Optional: exercise get_pipe / create_label against a known test pipe
export PIPE_BUILDING_LIVE_PIPE_ID=123456789

# Optional: exercise create_pipe (creates a new pipe each run)
export PIPE_BUILDING_LIVE_ORG_ID=300514213

uv run pytest tests/tools/test_pipe_config_tools_live.py -m integration -v
```

### Updating GraphQL Schema
If you are contributing and need to update the Pipefy GraphQL definitions:

```bash
uv run gql-cli https://app.pipefy.com/graphql --print-schema --schema-download --headers 'Authorization: Bearer <AUTH_TOKEN>' > tests/services/pipefy/schema.graphql
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
