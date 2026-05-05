# Python runtime dependencies

This document explains **why** the main third-party packages in [`pyproject.toml`](../pyproject.toml) are required. It complements the short summary in the README (*Getting started → Why these dependencies?*).

## httpx

**Role:** Async HTTP client for every non-trivial network path in the server.

**Where it is used:**

- **GraphQL (public Pipefy API)** — `gql` uses `HTTPXAsyncTransport` (see `pipefy_mcp.services.pipefy.base_client`).
- **Internal Pipefy GraphQL** — `InternalApiClient` uses `httpx.AsyncClient` with timeouts (`pipefy_mcp.services.pipefy.internal_api_client`).
- **Attachments** — Presigned URL upload/download flows (`pipefy_mcp.services.pipefy.attachment_service`, `pipefy_mcp.tools.attachment_tools`).
- **Exports** — Downloading signed HTTPS URLs before parsing or streaming (`pipefy_mcp.services.pipefy.observability_export_csv`).

**Why httpx (and not e.g. sync `requests` alone):** the codebase is async end-to-end for MCP handlers and GraphQL; one client family keeps timeouts, connection limits, and error types consistent.

## httpx-auth

**Role:** OAuth2 **client credentials** for Pipefy service accounts (token fetch and refresh).

**Where it is used:**

- Passed into GraphQL transport setup and into direct `httpx` clients that must use the same Pipefy OAuth settings — see imports of `OAuth2ClientCredentials` under `pipefy_mcp.services.pipefy/`.

**Why a dedicated auth helper:** avoids hand-rolling refresh and header injection; aligns all authenticated HTTP with the same credential source as Pydantic Settings.

## openpyxl

**Role:** Read `.xlsx` workbooks and turn sheet data into text the MCP can return (CSV-like).

**Where it is used:**

- `pipefy_mcp.services.pipefy.observability_export_csv` — `load_workbook` on downloaded export bytes, first worksheet to CSV with optional size limits.

**Why openpyxl:** some Pipefy exports are delivered as Excel files, not plain CSV; a dedicated reader is the reliable way to extract rows without fragile format guesses.

## Supply-chain and security notes

- Prefer **pinned versions** in `pyproject.toml` as the project already does; review upgrades in PRs with a quick grep for breaking API usage.
- Export downloads use **HTTPS** and host allowlisting in code (see `is_allowed_pipefy_export_download_url` in `observability_export_csv`); do not bypass those checks when extending download paths.
