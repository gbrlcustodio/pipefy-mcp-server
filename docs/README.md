# Documentation index

This folder holds **human-facing** guides for the Pipefy Labs monorepo. Use the sections below to load only the context you need.

## By surface

| Area | Path | Contents |
|------|------|----------|
| **MCP server** | [`docs/mcp/`](mcp/README.md) | MCP tool reference (`mcp/tools/`), conventions shared by tools |
| **CLI** | [`docs/cli/`](cli/README.md) | Typer usage patterns, discover-then-execute flows |
| **SDK** | [`docs/sdk/`](sdk/README.md) | Using `pipefy-sdk` as a library (within or outside the workspace) |

## Shared (all packages)

| Doc | Role |
|-----|------|
| [`setup.md`](setup.md) | First-time install, `PIPEFY_*` variables, MCP client JSON samples |
| [`parity.md`](parity.md) | MCP tool ↔ CLI command matrix (source of truth for coverage and deferrals) |
| [`MIGRATION.md`](MIGRATION.md) | Notes for existing MCP users across packaging changes |
| [`dependencies.md`](dependencies.md) | Why each runtime dependency exists |

Package-level READMEs under `packages/*/README.md` link back here for install and parity details.
