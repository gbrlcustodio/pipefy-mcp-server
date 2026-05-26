# Changelog

All notable changes to this repository are documented in this file.

Releases are versioned in lockstep across workspace members (`pipefy-sdk`, `pipefy-mcp-server`, `pipefy-cli`).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **CLI**: `pipefy auth status [--json|-j]` — reports auth source, identity, session expiry, and exit codes.
- **CLI**: `pipefy auth logout` — revokes the refresh token at the IdP and clears the stored session.
- **Auth**: `AuthSettings.auth_url` now defaults to the Pipefy production IdP when `PIPEFY_AUTH_URL` is unset — removes the previous `PIPEFY_AUTH_URL is required` exit-2 friction on `pipefy auth login` / `pipefy auth logout` and wires the MCP stored-session tier automatically after `pipefy auth login`. Override by setting `PIPEFY_AUTH_URL=<url>` to a non-prod IdP. Closes #233.
- **SDK / Auth**: introduced `PIPEFY_BASE_URL` (default `https://app.pipefy.com`) that drives the four API endpoints (`graphql_url`, `internal_api_url`, `interfaces_graphql_url`, `service_account_url`) as pydantic `@computed_field` properties. Operators on non-prod environments set `PIPEFY_BASE_URL=<host>` once and all four endpoints follow. The OIDC issuer (`PIPEFY_AUTH_URL`, default `https://signin.pipefy.com/realms/pipefy`) remains a separate full-URL field because non-prod realm names don't follow a derivable convention. Closes #238.
- **MCP**: stored-session tier wired into `ServicesContainer`; setting `PIPEFY_AUTH_URL` after `pipefy auth login` now lets the MCP server reuse the keychain-backed session, with the refresh pre-warmed at startup so a stale or revoked session surfaces before the first tool call.

### Changed

- **SDK / MCP / CLI**: renamed the two service-account credential env vars for clarity and to remove the one-letter footgun against `PIPEFY_AUTH_URL` (interactive user-login issuer): `PIPEFY_OAUTH_CLIENT` → `PIPEFY_SERVICE_ACCOUNT_CLIENT_ID`, `PIPEFY_OAUTH_SECRET` → `PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET`. `PIPEFY_OAUTH_URL` is dropped without a renamed counterpart — the OAuth token endpoint now derives from `PIPEFY_BASE_URL` (see the **Removed** section). Closes #127.
- **Auth / SDK**: every `PIPEFY_*` env var is validated against a semantically meaningful pattern at settings construction. URL env vars (`PIPEFY_BASE_URL`, `PIPEFY_AUTH_URL`) require `https?://` plus non-whitespace; credential fields (`PIPEFY_TOKEN`, `PIPEFY_SERVICE_ACCOUNT_CLIENT_ID`, `PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET`, `PIPEFY_AUTH_CLIENT_ID`) reject leading / trailing whitespace; `PIPEFY_ORG_ID` must be an ASCII numeric string. There is no longer an empty-string opt-out for any tier — unset the variable to fall back to the default (kill-switch tracked separately in #237).
- **SDK / MCP / CLI**: renamed `--graphql-url` CLI flag to `--base-url` to match the new env-var shape.

### Deprecated

- **SDK**: legacy `PIPEFY_OAUTH_*` env vars still resolve to the new `service_account_*` fields via an alias shim, with a one-shot stderr deprecation warning per legacy key. The aliases will be removed in a later `0.2.0-beta.x` release (carrying an explicit breaking-change callout). See [`docs/MIGRATION.md`](docs/MIGRATION.md#service-account-env-var-rename).

### Fixed

- **CLI**: concurrent `pipefy` invocations near token expiry no longer surface `invalid_grant` errors; the refresh-token grant is now serialized across processes via a filesystem lock at `~/.config/pipefy/refresh.lock` (`%APPDATA%/pipefy/refresh.lock` on Windows). Closes #133.

### Removed

- **HARD BREAK** — per-URL env vars dropped in favor of `PIPEFY_BASE_URL` + `PIPEFY_AUTH_URL`. The following env vars are no longer recognized; `PipefySettings` / `AuthSettings` are configured with `extra="ignore"`, so settings construction silently drops them with no exception or warning — stale `.env` keys look configured but the prod defaults still apply. Same wording as `docs/MIGRATION.md`. Audit `.env`, MCP client JSON, and CI secrets before upgrading:
  - `PIPEFY_GRAPHQL_URL` — set `PIPEFY_BASE_URL` to your API host (graphql_url derives as `<base>/graphql`).
  - `PIPEFY_INTERNAL_API_URL` — derives as `<base>/internal_api`.
  - `PIPEFY_INTERFACES_GRAPHQL_URL` — derives as `<base>/graphql/interfaces`.
  - `PIPEFY_SERVICE_ACCOUNT_URL` — derives as `<base>/oauth/token`.
  - `PIPEFY_OAUTH_URL` (legacy alias for `PIPEFY_SERVICE_ACCOUNT_URL`) — no replacement; same derivation path.

  Migration: replace the five per-URL env vars with a single `PIPEFY_BASE_URL` (default `https://app.pipefy.com`). If you need a non-prod OIDC issuer, also set `PIPEFY_AUTH_URL` to the full issuer URL.
- **HARD BREAK** — user TOML config file `~/.config/pipefy/config.toml` is no longer read by either the CLI or the MCP server. Operators who relied on it must move credentials and `base_url` into shell environment variables, a `.env` file at the working directory, or their MCP client's `env` block. Two config surfaces (env + `.env`) instead of three; persistent global config is shell-rc territory.
- `PIPEFY_TENANT` / `PIPEFY_AUTH_REALM` env vars (never shipped in a release; existed only on intermediate commits of this branch).
- **Auth**: `pipefy_auth.DEFAULT_AUTH_URL` constant (and its re-export from the package root). Callers should consult the resolved `AuthSettings.auth_url` instead.
- **CLI**: `pipefy skills list` / `pipefy skills show` Typer subcommands and the bundled `packages/cli/src/pipefy_cli/skills/*.md` starter pack. Install the full catalog via [`skills.sh`](https://github.com/vercel-labs/skills) (`npx skills add gbrlcustodio/pipefy-mcp-server`) or reference the canonical files under `skills/<domain>/<skill>/SKILL.md` directly. Closes #230.
- **Tooling**: `scripts/sync_starter_pack.py` (canonical files at `skills/<domain>/<skill>/SKILL.md` are now the only source).
- **CLI**: `pyyaml` dependency of `pipefy-cli` (only consumer was the deleted `skills` command).

## [0.2.0-beta.1] - 2026-05-18

Monorepo **Pipefy Labs** public beta on the `v0.2.0-beta.*` line (GitHub Release + wheels only; no PyPI until `v1.*`). Tag **`v0.2.0-beta.1`** matches `__version__` in all workspace packages per `RELEASE.md`.

### Added

- **CLI**: added MCP-parity commands for core workflow domains: `pipe`, `phase`,
  `field`, `table`, `record`, `label`, `webhook`, `relation`, and `member`.
- **CLI**: added post-v0.1 parity domains: `attachment`, `field-condition`,
  `email`, `audit`, `automation`, `introspect`, `graphql`, `agent`,
  `ai-automation`, `usage`, `report-pipe`, `report-org`, `export`, and `org`.
- **MCP / CLI**: shared SDK facade covers attachment upload, automation
  preflight, field-condition normalization, AI prompt and behavior validation,
  report export streaming, and service-account guard helpers.
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
- **CLI**: OAuth client-credentials auth (`PIPEFY_OAUTH_*`; renamed to `PIPEFY_SERVICE_ACCOUNT_*` in the Unreleased section) and `--token` / `PIPEFY_TOKEN` static bearer override; auth precedence flag > env > `~/.config/pipefy/config.toml`.
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
- **SDK**: `PipeConfigService.update_phase_field` accepts optional `phase_id` / `pipe_id` and resolves a slug-like `field_id` to the field's `uuid` (injected as `input.uuid` while the slug stays as `input.id`, matching Pipefy's `UpdatePhaseFieldInput` contract). The pipe-wide lookup runs phase fetches concurrently via `asyncio.gather`; partial phase-fetch failures raise an actionable `ValueError` instead of returning an ambiguous match. Surfaced through MCP `update_phase_field(phase_id=…, pipe_id=…)` and CLI `pipefy field update --extra '{"phase_id":"…"}'`.
- **MCP**: `delete_phase_field` preview now enumerates `dependents.field_conditions` even when the rule only references the field in expression `field_address` (not just `actions[].phaseFieldId`); the condition tree walker has a defensive depth cap of 16.
- **SDK / MCP**: `PipefyClient.get_automation_logs_by_repo` short-circuits to an empty page when the pipe has no automations (was returning `MULTIPLE_INVALID_INPUT: Automation_ids can't be blank` from the API).
- **SDK / MCP**: `invite_members` validates each row with a new `MemberInvite` Pydantic model (`EmailStr` + non-blank `role_name`, lowercase normalization, `extra="forbid"`) and raises a single-line `ValueError` pointing at the offending field. MCP surfaces it as `INVALID_ARGUMENTS`.
- **SDK**: `ai_preflight.validate_ai_automation_prompt_sdk` flags overlap when the same `%{internal_id}` appears both in the prompt and in `field_ids`, in English, citing the API rejection message.
- **MCP**: `find_records` returns the unified envelope `pagination={has_more, end_cursor, page_size}` (snake_case) when the unified envelope flag is on, matching `get_table_records`.
- **MCP / CLI docs**: `create_card`, `create_table_record`, `clone_pipe`, and `create_field_condition` docstrings clarify title-derivation quirks, async clone phases, and the `phaseFieldId` discovery path.
- **SDK**: `MemberInvite` lives at `pipefy_sdk.MemberInvite` (re-exported in the top-level `__all__`); `slug_like_field_token` / `looks_like_uuid_token` extracted to `pipefy_sdk.utils.field_tokens` for reuse across services.

### Removed
