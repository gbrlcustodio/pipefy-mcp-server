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
| [`uninstall.md`](uninstall.md) | `uninstall.sh --scan` and teardown, and switching between the hosted, local, and plugin channels |
| [`parity.md`](parity.md) | MCP tool ↔ CLI command matrix (source of truth for coverage and deferrals) |
| [`MIGRATION.md`](MIGRATION.md) | Notes for existing MCP users across packaging changes |
| [`dependencies.md`](dependencies.md) | Why each runtime dependency exists |
| [`architecture.md`](architecture.md) | Intra-package layering, type ownership at boundaries, ports, and alternative constructors |
| [`response-typing.md`](response-typing.md) | When to parse a GraphQL response into a validating model vs. leave it a `TypedDict` |
| [`ipaas.md`](ipaas.md) | iPaaS (Advanced Automations) tools: meta-tool pattern, flow overview, vocabulary |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | Contributing skills (Markdown playbooks) |
| [`../RELEASE.md`](../RELEASE.md) | Versioning and GitHub Releases |
| [`../TERMS.md`](../TERMS.md) | Repository terms notice (license, platform terms, disclaimers) |
| [`../SECURITY.md`](../SECURITY.md) | Vulnerability disclosure |
| [`compliance/COMPLIANCE.template.md`](compliance/COMPLIANCE.template.md) | Stub for per-blueprint `COMPLIANCE.md` / AI Compliance Card |

First-time install and per-client MCP wiring live in the root [`README.md#installation`](../README.md#installation) (including the [Cursor Marketplace plugin](../README.md#6-cursor-marketplace-plugin)). First-time agent checklist (path choice, ask-your-agent, verify): [`skills/onboarding/pipefy-toolkit-setup/SKILL.md`](../skills/onboarding/pipefy-toolkit-setup/SKILL.md). Package READMEs under `packages/*/README.md` cover surface-specific edge cases.
