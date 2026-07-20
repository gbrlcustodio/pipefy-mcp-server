# Documentation index

Human-facing guides for the **[pipefy/ai-toolkit](https://github.com/pipefy/ai-toolkit)** monorepo (packages: `pipefy-mcp-server`, `pipefy-cli`, `pipefy`). Use the sections below to load only the surface you need.

## By surface

| Area | Path | Contents |
|------|------|----------|
| **MCP server** | [`docs/mcp/`](mcp/README.md) | MCP tool reference (`mcp/tools/`), conventions shared by tools |
| **CLI** | [`docs/cli/`](cli/README.md) | Typer usage patterns, discover-then-execute flows |
| **SDK** | [`docs/sdk/`](sdk/README.md) | Using `pipefy` as a library (within or outside the workspace) |

## Shared (all packages)

| Doc | Role |
|-----|------|
| [`config.md`](config.md) | `PIPEFY_*` environment variables, `config.toml` schema and path, precedence chain |
| [`cli/auth.md`](cli/auth.md) | CLI credential precedence, `pipefy auth login`, troubleshooting |
| [`parity.md`](parity.md) | MCP tool ↔ CLI command matrix (source of truth for coverage and deferrals) |
| [`MIGRATION.md`](MIGRATION.md) | Notes for existing MCP users across packaging changes |
| [`dependencies.md`](dependencies.md) | Why each runtime dependency exists |
| [`architecture.md`](architecture.md) | Intra-package layering, type ownership at boundaries, ports, and alternative constructors |
| [`ipaas.md`](ipaas.md) | iPaaS (Advanced Automations) tools: meta-tool pattern, flow overview, vocabulary |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | Contributing skills (Markdown playbooks) |
| [`../RELEASE.md`](../RELEASE.md) | Versioning and GitHub Releases |

First-time install and per-client MCP wiring live in the root [`README.md#installation`](../README.md#installation). Package READMEs under `packages/*/README.md` cover surface-specific edge cases.
