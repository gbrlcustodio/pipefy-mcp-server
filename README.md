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
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python 3.12+" /></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/uv-package%20manager-blueviolet" alt="uv package manager" /></a>
  <a href="https://modelcontextprotocol.io/introduction"><img src="https://img.shields.io/badge/MCP-Server-orange" alt="MCP Server" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License" /></a>
</p>

> **⚠️ Disclaimer:** This is a "Build in public" project primarily aimed at developer workflows. It is **not** the official, supported Pipefy integration for external enterprise clients, but rather a tool to facilitate the development experience for those who use Pipefy for task management.

## Table of contents
<p align="center">
  <a href="#feature-overview">Feature overview</a> •
  <a href="#getting-started">Getting started</a> •
  <a href="#usage-with-cursor">Usage with Cursor</a> •
  <a href="#development--testing">Development & Testing</a> •
  <a href="#contributing">Contributing</a>
</p>

## Feature Overview

This server exposes common Kanban actions as "tools" that LLMs (like Claude Sonnet 4.5 inside Cursor) can invoke. The codebase follows a clean architecture with a facade pattern delegating to domain-specific services (Pipe and Card operations), keeping GraphQL queries and utilities organized in separate modules.

### Pipe Tools

* **`get_pipe`**: Get details about a pipe's structure, including phases, labels, and start form fields.
* **`get_start_form_fields`**: Inspect the schema of a pipe's start form. Use this to let the Agent know which fields are required *before* it tries to create a card.

### Card Tools

* **`get_cards`**: List and search for cards in a specific pipe (allows the Agent to understand your backlog).
* **`get_card`**: Retrieve full details of a specific card.
* **`create_card`**: Create a new card (e.g., report a bug found while coding without leaving the IDE).
    * **Elicitation**: Elicitation is an MCP feature that allows the server to request additional information from the user mid-tool-execution. This server uses MCP's elicitation feature to prompt the user for required field values before creating the card.

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

* **`move_card_to_phase`**: Move a card to a different phase (e.g., move a task to "Code Review" after pushing a PR).
* **`update_card_field`**: Update a single field of an existing card via `updateCardField` (simple, full replacement of that field's value).
* **`update_card`**: Update card attributes (title, assignees, labels, due date) and/or multiple custom fields using `updateCard` and `updateFieldsValues`.

### Card update tools: when to use each

- **Use `update_card_field`** when you only need to change *one* field on a card (for example, updating a status, a text field, or a single label value) and you are fine replacing the entire value for that field in one shot.
- **Use `update_card` with `field_updates`** when you want to update **one or more custom fields at once** by ID, replacing their values (the server converts this to `updateFieldsValues` with `REPLACE` under the hood).
- **Use `update_card` with attribute parameters** (`title`, `assignee_ids`, `label_ids`, `due_date`) when you need to update card metadata. These can be combined with `field_updates` in a single call.

## Getting Started

### Prerequisites
Installing the server requires the following on your system:
- Python 3.12+
- A **Pipefy Service Account Token** (Generate in Admin Panel > Service Accounts).
- Rembember to add the Service account to the pipe you want the AI to use.

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
