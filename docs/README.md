# Documentation index

Human-facing guides for the **[pipefy/ai-toolkit](https://github.com/pipefy/ai-toolkit)** monorepo (applications: `pipefy-mcp-server`, `pipefy-cli`, `pipefy`). Use the sections below to load only the application you need.

## By application

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
| [`uninstall.md`](uninstall.md) | `uninstall.sh --scan` and teardown, and switching between the hosted, local, and plugin channels |
| [`parity.md`](parity.md) | MCP tool ↔ CLI command matrix (source of truth for coverage and deferrals) |
| [`MIGRATION.md`](MIGRATION.md) | Notes for existing MCP users across packaging changes |
| [`contributing/dependencies.md`](contributing/dependencies.md) | Why each runtime dependency exists |
| [`contributing/architecture.md`](contributing/architecture.md) | Map of the architecture: the quality goals and constraints that shape it, the boundary with its diagram, the decomposition into applications, packages, and layers, one runtime scenario, the rules that cross every package, the known debt, and the glossary |
| [`contributing/conventions.md`](contributing/conventions.md) | Code conventions, as rules with permanent IDs. A rule belongs there when a reviewer applies it by judgment to one unit of code |
| [`ipaas.md`](ipaas.md) | iPaaS (Advanced Automations) tools: meta-tool pattern, flow overview, vocabulary |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | Contributing skills (Markdown playbooks) |
| [`../RELEASE.md`](../RELEASE.md) | Versioning and GitHub Releases |
| [`../TERMS.md`](../TERMS.md) | Repository terms notice (license, platform terms, disclaimers) |
| [`../SECURITY.md`](../SECURITY.md) | Vulnerability disclosure |
| [`compliance/COMPLIANCE.template.md`](compliance/COMPLIANCE.template.md) | Stub for per-blueprint `COMPLIANCE.md` / AI Compliance Card |

First-time install and per-client MCP wiring live in the root [`README.md#installation`](../README.md#installation). First-time agent checklist (path choice, ask-your-agent, verify): [`skills/onboarding/pipefy-toolkit-setup/SKILL.md`](../skills/onboarding/pipefy-toolkit-setup/SKILL.md). Each README under `packages/*/README.md` covers the edge cases of its own package.
