# MCP server for Pipefy

<p align="center">
  <strong>Pipefy MCP is an open-source MCP server that lets your IDE safely create cards, update field information, and use any Pipefy resource — all with built-in safety controls.</strong>
</p>

<p align="center">
  ⚡ Free & open-source forever.
  📢 Share your feedback on GitHub issues or at dev@pipefy.com.
</p>
<p>

<p align="center">
  <a href="https://pypi.org/project/pipefy-mcp-server/"><img src="https://img.shields.io/pypi/v/pipefy-mcp-server.svg" alt="PyPI version" /></a>
  <a href="https://github.com/gbrlcustodio/supabase-mcp-server/actions"><img src="https://github.com/gbrlcustodio/pipefy-mcp-server/workflows/CI/badge.svg" alt="CI Status" /></a>
  <a href="https://codecov.io/gh/gbrlcustodio/supabase-mcp-server"><img src="https://codecov.io/gh/gbrlcustodio/pipefy-mcp-server/branch/main/graph/badge.svg" alt="Code Coverage" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python 3.12+" /></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/uv-package%20manager-blueviolet" alt="uv package manager" /></a>
  <a href="https://pepy.tech/project/pipefy-mcp-server"><img src="https://static.pepy.tech/badge/pipefy-mcp-server" alt="PyPI Downloads" /></a>
  <a href="https://smithery.ai/server/@gbrlcustodio/pipefy-mcp-server"><img src="https://smithery.ai/badge/@gbrlcustodio/supabase-mcp-server" alt="Smithery.ai Downloads" /></a>
  <a href="https://modelcontextprotocol.io/introduction"><img src="https://img.shields.io/badge/MCP-Server-orange" alt="MCP Server" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License" /></a>
</p>


## Table of contents
<p align="center">
  <a href="#getting-started">Getting started</a> •
  <a href="#feature-overview">Feature overview</a> •
  <a href="#troubleshooting">Troubleshooting</a> •
  <a href="#changelog">Changelog</a>
</p>

## Getting Started

### Prerequisites
Installing the server requires the following on your system:
- Python 3.12+

If you plan to install via `uv`, ensure it's [installed](https://docs.astral.sh/uv/getting-started/installation/#__tabbed_1_1).

### Inspecting locally developed servers
To inspect servers locally developed or downloaded as a repository, the most common way is:

```sh
npx @modelcontextprotocol/inspector uv --directory . run pipefy-mcp-server
```

## Testing

### Updating GraphQL Schema

```sh
uv run gql-cli https://app.pipefy.com/graphql --print-schema --schema-download --headers 'Authorization: Bearer <AUTH_TOKEN>' > tests/services/pipefy/schema.graphql
```
