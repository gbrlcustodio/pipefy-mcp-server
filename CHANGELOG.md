# Changelog

All notable changes to this repository are documented in this file.

Releases are versioned in lockstep across workspace members (`pipefy-sdk`, `pipefy-mcp-server`, `pipefy-cli`).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **CLI**: `pipefy skills list` and `pipefy skills show <name>` for browsing the bundled
  starter pack (8 high-impact Pipefy workflows), with YAML frontmatter parsing for
  descriptions.
- **Skills**: `skills/` catalog with authoring guide, contributing rules, and
  `skills-lint.yml` CI (frontmatter, starter-pack bundle drift, MCP/CLI reference lint,
  and `pipefy skills list` smoke).
- **Docs**: `docs/MIGRATION.md` cutover guide for existing `pipefy-mcp-server` users.
- **Tooling**: `scripts/sync_starter_pack.py` copies canonical starter-pack `SKILL.md`
  files into `packages/cli/src/pipefy_cli/skills/`; use `--check` in CI or before release.
- **CLI**: introduce `pipefy-cli` workspace package with `pipefy` entry point.
- **CLI**: `pipefy card get <id>` (mirrors MCP `get_card`) with `--json` / Rich rendering.
- **CLI**: OAuth client-credentials auth (`PIPEFY_OAUTH_*`) and `--token` / `PIPEFY_TOKEN` static bearer override; auth precedence flag > env > `~/.config/pipefy/config.toml`.
- **CLI**: `--graphql-url` and `--allow-insecure-urls` global flags; same SSRF policy as MCP.
- **CLI**: shell completion via `pipefy --install-completion bash|zsh`.
- **SDK**: optional `bearer_token=` constructor on `PipefyClient` and `StaticBearerAuth` in `base_client` (transport auth path used by the CLI `--token` / `PIPEFY_TOKEN`).

### Changed

- **Docs**: MCP tool reference moved to `docs/mcp/tools/`; added `docs/README.md`, `docs/mcp/README.md`, `docs/cli/README.md`, and `docs/sdk/README.md` as surface-oriented entry points. `docs/setup.md` and `docs/parity.md` paths unchanged for stable links.
- **SDK**: PyPI distribution renamed from `pipefy-ai-sdk` to `pipefy-sdk` (import package remains `pipefy_sdk`). Update installs and `uv add` / `pip install` references accordingly.
- **CLI / MCP**: Creating a traditional automation with `card_moved` + `move_single_card` runs SDK move-transition preflight first, returning a clear validation error when the destination phase is unreachable from the source phase (instead of opaque GraphQL failures).
- Internal: repository reorganized as a uv workspace; ``pipefy-mcp-server`` distribution and runtime behavior unchanged.

### Fixed

- **CLI**: `pipefy agent update` resolves slug-style `fieldId` values in behaviors for error-path enrichment the same way as the happy path (via `PipefyClient.update_ai_agent`), so `RECORD_NOT_SAVED` diagnostics do not falsely blame slug tokens as unknown pipe fields.
- **CLI / MCP**: `field-condition create` / `update` accept legacy `actionId: "hidden"` on condition actions; the SDK normalizes to `hide` before mutations.

### Removed
