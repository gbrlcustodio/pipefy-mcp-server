# Python runtime dependencies

This document explains **why** the main third-party packages exist across the **uv workspace**. Values and pins live in each package’s `pyproject.toml` (`packages/sdk`, `packages/mcp`, `packages/cli`). Use **[`docs/setup.md`](setup.md)** for install and env vars.

## pipefy-sdk (`packages/sdk`)

| Dependency | Role |
| --- | --- |
| `gql[httpx]` | Async GraphQL client; `HTTPXAsyncTransport` for Pipefy’s GraphQL endpoints. |
| `httpx` | Shared async HTTP for transports and direct calls (timeouts, HTTP/2-capable stack via httpx). |
| `httpx-auth` | OAuth2 client-credentials (`OAuth2ClientCredentials`) aligned with Pipefy service accounts. |
| `pydantic` / `pydantic-settings` | Request/response models and typed configuration (`PipefySettings`). |
| `email-validator` | Used where models validate email-shaped inputs (e.g. member invites). |
| `rapidfuzz` | Fuzzy matching helpers used in domain logic where the SDK mirrors MCP/CLI behavior. |
| `openpyxl` | Reads `.xlsx` exports and converts sheet data to text (CSV-like) when the API returns Excel. |

**Security:** GraphQL and export URLs are validated against SSRF rules in SDK services; do not bypass host checks when adding download paths.

## pipefy-mcp-server (`packages/mcp`)

| Dependency | Role |
| --- | --- |
| `pipefy-sdk` | All GraphQL and domain logic (facade + services). |
| `mcp[cli]` | MCP protocol server runtime and CLI entry for `pipefy-mcp-server`. |
| `httpx` | Attachment downloads and any direct HTTP outside `gql` (same family as the SDK). |
| `pydantic` / `pydantic-settings` | Tool inputs and server settings. |

## pipefy-cli (`packages/cli`)

| Dependency | Role |
| --- | --- |
| `pipefy-sdk` | Same GraphQL facade as MCP; CLI is a thin Typer layer. |
| `typer` | Command groups, options, and exit-code mapping. |
| `rich` | Human-readable tables and summaries when `--json` is not used. |
| `pydantic-settings` | Loads `PIPEFY_*` the same way as MCP/SDK. |

## Supply-chain notes

- Prefer **pinned versions** as committed in each `pyproject.toml`; review upgrades with a quick grep for breaking API usage.
- Prefer **HTTPS** for every Pipefy and webhook URL; optional insecure URLs are dev-only and documented in `.env.example`.
