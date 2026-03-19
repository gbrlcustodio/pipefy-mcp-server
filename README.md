# PipeClaw 🦞 - The agentic honey badger with claws

Pipefy's MCP server for **PipeClaw**. It exposes a focused set of **tools** so AI agents can work with pipes, cards, comments, AI automations and AI agents, using the same GraphQL API your org already trusts.

**Why we’re building it:** this is the MCP layer we ship for **PipeClaw**—our agent stack on top of Pipefy—can **perform real actions inside the product** (pipes, cards, fields, automations and AI agents) through a single, maintainable tool surface instead of ad hoc integrations. 

The same tools work for other MCP clients (e.g. Cursor). When a dedicated tool is missing or Pipefy’s schema changes, **introspection** and optional **raw GraphQL** keep agents unblocked while still using your service account and the standard GraphQL endpoint.

## Contents

- [Tools](#tools)
  - [Pipe & form fields](#pipe--form-fields)
  - [Cards & comments](#cards--comments)
  - [Card updates: which tool?](#card-updates-which-tool)
  - [Introspection & raw GraphQL](#introspection--raw-graphql)
  - [AI automation](#ai-automation)
  - [AI agents](#ai-agents)
- [Getting started](#getting-started)
- [Usage with Cursor](#usage-with-cursor)
- [Development & testing](#development--testing)

## Tools

All tools target Pipefy’s **standard GraphQL** endpoint (`PIPEFY_GRAPHQL_URL`). Credentials are scoped by your **service account** (pipes and permissions you grant).

### Pipe & form fields

| Tool | Purpose |
|------|--------|
| **`get_pipe`** | Pipe structure: phases, labels, start form fields. |
| **`get_pipe_members`** | Members of a pipe. |
| **`get_start_form_fields`** | Start form field definitions (types, required, options). Use before **`create_card`**. |
| **`get_phase_fields`** | Fields for a phase (for phase-specific updates). |
| **`search_pipes`** | Find pipes across organizations (optional name filter). |

### Cards & comments

| Tool | Purpose |
|------|--------|
| **`get_cards`** | List/search cards in a pipe. Use `include_fields=true` for custom field name/value on each card. |
| **`find_cards`** | Cards where a field equals a value (`pipe_id`, `field_id`, `field_value`). Optional `include_fields`. |
| **`get_card`** | One card by ID. Optional `include_fields`. |
| **`create_card`** | Create a card; may use MCP **elicitation** for required fields when supported. |
| **`add_card_comment`** / **`update_comment`** / **`delete_comment`** | Comment lifecycle by `card_id` / `comment_id` and text where applicable. |
| **`move_card_to_phase`** | Move a card to another phase. |
| **`delete_card`** | **Destructive.** Preview first; set `confirm=true` to delete. |
| **`fill_card_phase_fields`** | Fill phase fields (with elicitation when available). |
| **`update_card_field`** | Update a **single** custom field (`updateCardField`). |
| **`update_card`** | Card metadata (`title`, assignees, labels, due date) and/or multiple fields via `field_updates` (`updateCard` / `updateFieldsValues`). |

### Card updates: which tool?

- **`update_card_field`** — one field, full replacement for that field.
- **`update_card`** with **`field_updates`** — several custom fields in one call.
- **`update_card`** with **title / assignee_ids / label_ids / due_date** — metadata (can combine with `field_updates`).

### Introspection & raw GraphQL

These tools support **discovery** and a **last-resort execution path** when no dedicated tool fits or Pipefy changes the schema. They use the same OAuth-backed GraphQL client as the rest of Pipeclaw.

| Tool | Read-only hint | Purpose |
|------|----------------|--------|
| **`introspect_type`** | Yes | Inspect a GraphQL type: `fields`, `inputFields`, or `enumValues` (e.g. `Card`, `CreateCardInput`). |
| **`introspect_mutation`** | Yes | Inspect a root mutation: arguments, defaults, return type (e.g. `createCard`). |
| **`search_schema`** | Yes | Keyword search over type **names** and **descriptions** (case-insensitive; `__` introspection types excluded). |
| **`execute_graphql`** | **No** | Run an arbitrary query or mutation. Syntax is validated before the request. **Prefer dedicated tools when they exist.** Use **`introspect_mutation`** (and related types) before sending mutations. |

Responses are JSON formatted for readability in the agent (`success` / `result` or `error`). GraphQL **errors** from the transport are surfaced explicitly, not swallowed.

### AI automation

| Tool | Purpose |
|------|--------|
| **`create_ai_automation`** | Create a prompt-driven automation writing to card fields (requires AI enabled on the pipe). |
| **`update_ai_automation`** | Update name, prompt, fields, condition, or active flag. |

### AI agents

| Tool | Purpose |
|------|--------|
| **`create_ai_agent`** | Create an agent on a pipe (`repo_uuid` from **`get_pipe`**, not the numeric URL id). |
| **`update_ai_agent`** | Full agent payload: instruction + 1–5 behaviors (API replaces the whole config). |
| **`toggle_ai_agent_status`** | Enable or disable an agent without resending full configuration. |

## Getting started

### Prerequisites

- Python **3.12+**
- A **Pipefy service account** (Admin → Service Accounts) with access to the pipes the agent should use.

### Install

```sh
git clone https://gitlab.com/pipefy/vibe-coding/pipeclaw.git
cd pipeclaw
uv sync
```

Run the server locally:

```sh
uv run pipeclaw
```

## Usage with Cursor

Register Pipeclaw as an MCP server (Cursor **Settings → MCP**).

```json
{
    "mcpServers": {
        "pipeclaw": {
            "cwd": "/absolute/path/to/pipeclaw",
            "command": "uv",
            "args": ["run", "--directory", ".", "pipeclaw"],
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

## Development & testing

```bash
uv run pytest
uv run pytest --cov=src/pipefy_mcp/services/pipefy --cov-report=term-missing
```

**MCP Inspector**

```bash
npx @modelcontextprotocol/inspector uv --directory . run pipeclaw
```

**Built with [Cursor](https://cursor.com/)** using Composer 2.0, Claude Opus 4.6, GPT 5.3 Codex, Gemini 3.1 Pro and Kimi K2.5.
