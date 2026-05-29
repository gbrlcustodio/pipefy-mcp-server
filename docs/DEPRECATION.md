# Deprecation and versioning (post-1.0)

This policy applies **after v1.0.0**, when published `pipefy-cli` and `pipefy-mcp-server` follow public [semantic versioning](https://semver.org/) on PyPI. Before that milestone, interfaces may still change without the guarantees below.

## Version bumps

| Kind | When it ships | Allowed changes |
| --- | --- | --- |
| **MAJOR** (`X.0.0`) | Rare | **Breaking** removals or incompatible contract changes (see [Breaking changes](#breaking-changes-major-only)). |
| **MINOR** (`1.x.0`) | Regular cadence | **Additive** behavior: new CLI subcommands, new MCP tools, new optional SDK entry points, new documented JSON fields. Existing documented behavior stays compatible unless covered by an active [deprecation](#deprecation-period). |
| **PATCH** (`1.x.y`) | As needed | **Bug fixes** and documentation corrections only — no intentional contract changes that would break scripts or agents relying on **documented** semantics. |

## Surfaces in scope

1. **CLI** (`pipefy`): command and subcommand names, flag names and meanings, documented exit codes, and **machine-readable** output when `--json` is used (documented keys and value types).
2. **MCP** (`pipefy-mcp-server`): tool names, documented argument shapes, and stable fields in tool responses where `docs/mcp/` describes a contract.
3. **`pipefy-sdk` public API** (when consumed as a library): symbols and behaviors described as public in `docs/sdk/` and package `__init__` exports.

Responses from Pipefy’s GraphQL API may gain or reshape fields at any time; consumers should ignore unknown keys and follow vendor docs for domain semantics.

## Deprecation period

When maintainers intend to remove or incompatibly change a stable contract:

1. Record a **deprecation** in `CHANGELOG.md` under the next release section: what is deprecated, the replacement (if any), and that the change is governed by this file.
2. Keep the deprecated path **working** for at least **two MINOR releases** after the release that **first** documents the deprecation (warning emitted when practical). Removal or breaking change may occur no earlier than the third subsequent minor line (e.g. deprecated in `1.4.0` → earliest removal in `1.7.0`).

Patch releases must not skip or shorten this window.

## Breaking changes (MAJOR only)

These require a **MAJOR** version when applied to **stable, documented** behavior:

- Removing or renaming CLI commands or flags, or changing `--json` output incompatibly (removing documented fields or changing documented types).
- Removing or renaming MCP tools, or breaking documented tool input/output contracts.
- Removing or renaming public SDK APIs, or incompatible signature / behavior changes on documented public types and functions.

Non-breaking examples: clearer error strings, help text fixes, purely additive JSON fields, Rich layout tweaks that do not change `--json`.

## Related docs

- Root [`README.md#installation`](../README.md#installation) — install
- [`docs/config.md`](config.md) — environment variables and `config.toml`
- [`docs/parity.md`](parity.md) — MCP tool ↔ CLI matrix
- [`docs/MIGRATION.md`](MIGRATION.md) — packaging and config moves between eras
