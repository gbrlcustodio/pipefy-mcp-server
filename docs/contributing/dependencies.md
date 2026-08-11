# Python runtime dependencies

This document explains **why** the main third-party packages exist across the **uv workspace**. Values and pins live in each package's `pyproject.toml` (`packages/sdk`, `packages/mcp`, `packages/cli`, `packages/auth`, `packages/infra`). Install commands live in the root [`README.md#installation`](../../README.md#installation). The environment variable and `config.toml` reference is at [`docs/config.md`](../config.md).

## pipefy (`packages/sdk`)

| Dependency | Role |
| --- | --- |
| `gql[httpx]` | Async GraphQL client. `HTTPXAsyncTransport` for Pipefy's GraphQL endpoints. |
| `httpx` | Shared async HTTP for transports and direct calls (timeouts, HTTP/2-capable stack via httpx). |
| `httpx-auth` | OAuth2 client-credentials (`OAuth2ClientCredentials`) aligned with Pipefy service accounts. |
| `pydantic` / `pydantic-settings` | Request/response models and typed configuration (`PipefySettings`). |
| `email-validator` | Used where models validate email-shaped inputs, for example member invites. |
| `rapidfuzz` | Fuzzy matching helpers used in domain logic where the SDK mirrors MCP/CLI behavior. |
| `openpyxl` | Reads `.xlsx` exports and converts sheet data to text (CSV-like) when the API returns Excel. |

**Security:** GraphQL and export URLs are validated against SSRF rules in `pipefy-infra` (invoked from SDK services and `AuthSettings`); do not bypass host checks when adding download paths.

## pipefy-mcp-server (`packages/mcp`)

| Dependency | Role |
| --- | --- |
| `pipefy` | All GraphQL and domain logic (facade + services). |
| `mcp[cli]` | MCP protocol server runtime and CLI entry for `pipefy-mcp-server`. |
| `httpx` | Attachment downloads and any direct HTTP outside `gql` (same family as the SDK). |
| `pydantic` / `pydantic-settings` | Tool inputs and server settings. |
| `starlette` | The ASGI types this package names directly: the `Starlette` app `wire_hosted_observability` returns, and the `Request` the runtime and the identity resolvers take. Arrives via `mcp[cli]` too, but declared here because the imports are ours. |
| `uvicorn` | The ASGI server `run_server` drives on the `--transport http` path (`uvicorn.Config` / `uvicorn.Server`, `access_log=False`). Arrives via `mcp[cli]` too, but only under a `sys_platform != 'emscripten'` marker, so it is declared here because the import is ours and unconditional. |

## pipefy-cli (`packages/cli`)

| Dependency | Role |
| --- | --- |
| `pipefy` | Same GraphQL facade as MCP; CLI is a thin Typer layer. |
| `typer` | Command groups, options, and exit-code mapping. |
| `rich` | Human-readable tables and summaries when `--json` is not used. |
| `pydantic-settings` | Loads `PIPEFY_*` the same way as MCP/SDK. |

## pipefy-auth (`packages/auth`)

| Dependency | Role |
| --- | --- |
| `pipefy-infra` | Config loading, path discovery, and the SSRF checks that `AuthSettings` runs on every URL it accepts. |
| `keyring` / `keyrings.alt` | Persists the refresh-token-bearing session in the OS keychain. `keyrings.alt` supplies `PlaintextKeyring` where no native backend exists. |
| `httpx` | The OAuth flow calls this package makes directly: discovery, token, refresh, and revoke. |
| `httpx-auth` | `OAuth2ClientCredentials` for a service-account credential, the same class the SDK uses. |
| `pyjwt[crypto]` | RS256 validation of an inbound bearer, in the resource-server role. `[crypto]` pulls `cryptography`. |
| `pydantic` / `pydantic-settings` | Typed credential settings (`AuthSettings`) and the parsed token responses. |

## pipefy-infra (`packages/infra`)

| Dependency | Role |
| --- | --- |
| `pydantic` / `pydantic-settings` | The typed config models, the URL-shape validators, and the TOML settings source. |

This package declares nothing else. It is the leaf of the workspace graph, so it depends on the standard library and these two.

## Supply-chain notes

- Prefer **pinned versions** as committed in each `pyproject.toml`; review upgrades with a quick grep for breaking API usage.
- Prefer **HTTPS** for every Pipefy and webhook URL; optional insecure URLs are dev-only and documented in `.env.example`.
