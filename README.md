# MCP server for Pipefy

<p align="center">
  <strong>Pipefy MCP is an open-source MCP server that lets your IDE safely create cards, update field information, and use any Pipefy resource — all with built-in safety controls.</strong>
</p>

<p align="center">
  🚧 <strong>Alpha Release:</strong> Building in public. <br>
  📢 Share your feedback on GitHub issues or at dev@pipefy.com.
</p>

<p align="center">
  <a href="https://pypi.org/project/pipefy-mcp-server/"><img src="https://img.shields.io/pypi/v/pipefy-mcp-server.svg" alt="PyPI version" /></a>
  <a href="https://github.com/gbrlcustodio/pipefy-mcp-server/actions"><img src="https://github.com/gbrlcustodio/pipefy-mcp-server/workflows/CI/badge.svg" alt="CI Status" /></a>
  <a href="https://codecov.io/gh/gbrlcustodio/pipefy-mcp-server"><img src="https://codecov.io/gh/gbrlcustodio/pipefy-mcp-server/branch/main/graph/badge.svg" alt="Code Coverage" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python 3.12+" /></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/uv-package%20manager-blueviolet" alt="uv package manager" /></a>
  <a href="https://pepy.tech/project/pipefy-mcp-server"><img src="https://static.pepy.tech/badge/pipefy-mcp-server" alt="PyPI Downloads" /></a>
  <a href="https://smithery.ai/server/@gbrlcustodio/pipefy-mcp-server"><img src="https://smithery.ai/badge/@gbrlcustodio/pipefy-mcp-server" alt="Smithery.ai Downloads" /></a>
  <a href="https://modelcontextprotocol.io/introduction"><img src="https://img.shields.io/badge/MCP-Server-orange" alt="MCP Server" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License" /></a>
</p>

> **⚠️ Disclaimer:** This is a "Build in Public" project primarily aimed at developer workflows. It is **not** the official, supported Pipefy integration for external enterprise clients, but rather a tool to facilitate the development experience for those who use Pipefy for task management.

## Table of contents
<p align="center">
  <a href="#feature-overview">Feature overview</a> •
  <a href="#getting-started">Getting started</a> •
  <a href="#usage-with-cursor">Usage with Cursor</a> •
  <a href="#development--testing">Development & Testing</a> •
  <a href="#contributing">Contributing</a>
</p>

## Feature Overview

This server exposes common Kanban actions as "tools" that LLMs (like Claude 3.5 Sonnet inside Cursor) can invoke.

* **`get_cards`**: List and search for cards in a specific pipe (allows the Agent to understand your backlog).
* **`get_card`**: Retrieve full details of a specific card.
* **`get_pipe`**: Get details about a pipe's structure.
* **`get_start_form_fields`**: Inspect the schema of a pipe's start form. Use this to let the Agent know which fields are required *before* it tries to create a card.
* **`create_card`**: Create a new card (e.g., report a bug found while coding without leaving the IDE).
* **`move_card_to_phase`**: Move a card to a different phase (e.g., move a task to "Code Review" after pushing a PR).

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

## Contributing
We are building this in public and we need your feedback!

- Field Mapping: If you encounter a complex field type that the Agent doesn't fill correctly, please open an issue.
- New Tools: What other Pipefy actions would improve your workflow? Feel free to opens an issue or a PR explaining what it is and how would you use
