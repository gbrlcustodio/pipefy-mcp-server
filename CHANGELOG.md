# Changelog

All notable changes to this repository are documented in this file.

Releases are versioned in lockstep across workspace members (`pipefy-sdk`, `pipefy-mcp-server`, `pipefy-cli`).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **MCP**: opt-in OAuth 2.0 resource-server profile for the `--remote` HTTP transport. Setting `PIPEFY_MCP_RS_RESOURCE_SERVER_URL` activates it (no separate enable flag): the server validates an inbound `Authorization: Bearer` on every request (RS256 against the issuer's JWKS, issuer and expiry, optional audience), serves RFC 9728 protected-resource metadata, and returns `401` with a `WWW-Authenticate` challenge on a missing or invalid token. Token-validation knobs live in `pipefy_auth.JwtValidationSettings` (`PIPEFY_JWT_ISSUER_URL`, which defaults to the login issuer, plus `PIPEFY_JWT_AUDIENCE` / `PIPEFY_JWT_VERIFY_AUDIENCE` / `PIPEFY_JWT_JWKS_URI`); resource identity (`PIPEFY_MCP_RS_RESOURCE_SERVER_URL`, `PIPEFY_MCP_RS_REQUIRED_SCOPES`) stays in `pipefy_mcp.ResourceServerSettings`; `PIPEFY_ALLOW_INSECURE_URLS` covers both. The stdio profile is unchanged. Per-request on-behalf-of identity is not yet wired (#302), so even with a validated bearer every call runs as the single startup identity. Closes #301.
- **SDK / MCP / CLI / auth**: outbound Pipefy requests now carry client-identifying telemetry headers so the API can attribute traffic by surface and version. The GraphQL path (public, Interfaces, and Internal API endpoints) sends `User-Agent: pipefy-sdk/<version> (<surface>)`, `X-Client-Name: <surface>`, and `X-Client-Version: <version>`, where `<surface>` is `mcp`, `cli`, or `sdk`. The surface is stamped programmatically at each entry point's composition root: the MCP server passes `mcp`, the CLI `cli`, and direct SDK use keeps the `sdk` default. It is a `PipefyClient` constructor argument rather than configuration, so it is never read from env or TOML and a caller cannot forge it. OAuth requests to the sign-in host carry `User-Agent: pipefy-auth/<version>`, `X-Client-Name: auth`, and `X-Client-Version`, identifying the auth component rather than an API surface. The header builder lives in `pipefy_infra.telemetry` so the SDK and auth packages share one `User-Agent` format. Closes #336.

### Changed

- **SDK**: services now receive GraphQL execution through their constructor instead of inheriting it. A narrow `GraphQLExecutor` protocol is the seam; `HttpxGraphQLExecutor` (formerly `BasePipefyClient`) is the only httpx/gql adapter, and `PipefyClient` builds one executor per endpoint via `build_executors` and injects them. Tests inject a fake executor rather than monkeypatching `execute_query`.
- **SDK (breaking)**: the `InternalApiClient` class and its `pipefy_sdk` export are removed; the internal endpoint is now an `HttpxGraphQLExecutor` configured with `internal_api_url` and the `[code=…][correlation_id=…]` error formatter (build it via `build_executors(settings, auth).internal`). Service constructors no longer take `auth`, and `RelationService`/`PortalService`/`MemberService`/`WebhookService`/`PipeConfigService` now require their collaborators (no self-construct fallbacks).
- **SDK**: `PipefyClient` now constructs its internal API client during `__init__` (built from the same `settings` and `auth` as every other endpoint client), so `PipefyClient(settings, auth=...)` is fully wired after construction. The `set_internal_api_client` methods on `PipefyClient` and `PortalService` are removed; pass the internal API client through the `PortalService` constructor when composing it directly. The `PipefyClient.internal_api_available` property is also removed: the internal API client is always present, so the property was always `True`.
- **Plugin (Claude Code)**: renamed the OAuth slash command from `/login` to `/pipefy-login` (`commands/login.md` → `commands/pipefy-login.md`, frontmatter `name: pipefy-login`). The old `name: login` claimed the `/login` trigger and shadowed Claude Code's built-in `/login` (Claude account sign-in): selecting the built-in entry in the command picker still ran the Pipefy command, so Claude login was unreachable via `/login` while the plugin was installed. Closes #331.

### Removed

- **SDK / MCP / CLI (breaking)**: retired the `PIPEFY_SERVICE_ACCOUNT_IDS` env var and the `service_account_ids` setting (and its TOML key). This drops the advisory features it fed: the guard that blocked `remove_member_from_pipe` from removing a configured service account, the `set_role` write-permission warning, and the proactive cross-pipe membership check in `validate_ai_agent_behaviors`. The Pipefy API still authorizes every mutation, so removing a service account is recoverable via the Pipefy UI, and the cross-pipe membership requirement now surfaces as a bare `PERMISSION_DENIED` at call time (recover with `get_pipe_members` + `invite_members`). The field was an advisory, single-tenant shadow of a missing platform attribute and had no place in the remote multi-user profile.

## [0.2.0-beta.4] - 2026-06-19

### Added

- **SDK / MCP / CLI**: `create_card` accepts optional `phase_id` and passes `title` on GraphQL `CreateCardInput` (mutation `createCard(input: $input)`). MCP: interactive `phase_id` elicits start-form fields; non-empty `fields` are filtered against `get_phase_fields(phase_id)` and `get_start_form_fields(pipe_id)`; agent seeding should set `skip_elicitation=true`. CLI: `pipefy card create <pipe_id> --phase-id <id>` (optional `--title`; emits `title_warning` when the API overrides the requested title).
- **MCP / CLI**: `get_phase_allowed_move_targets` lists valid destination phases for `move_card_to_phase` (GraphQL `phase.cards_can_be_moved_to_phases`). MCP returns normalized `{phase_id, phase_name, allowed_phases}`; CLI: `pipefy phase targets <phase_id>`.
- **SDK / MCP / CLI**: `get_phase_cards_count` reads native `Phase.cards_count` (MCP/CLI return `{phase_id, phase_name, cards_count}` via `get_phase`). `get_phase_cards` lists cards in a phase via `Phase.cards` pagination (`first` default 50, `after`, optional fields). CLI: `pipefy phase count <phase_id>`, `pipefy phase cards <phase_id> --first --after`.
- **SDK / MCP / CLI**: `get_pipe` selects `cards_count` on each workflow phase in `phases[]` (start-form intake stays on `start_form_fields`).
- **SDK / MCP / CLI**: report create/update/export paths preflight `filter` as nested `ReportCardsFilter` (`operator` + `queries`) in the SDK before GraphQL; reject naive top-level keys such as `current_phase`; coerce integer `value` scalars to strings. MCP and CLI surface the same error; CLI rejects invalid filters before auth.

### Changed

- **SDK / MCP / CLI (label color)**: `create_label` and `update_label` validate `color` as hex `#RGB` or `#RRGGBB` in the SDK before GraphQL (e.g. `red` is rejected with `expected #RGB or #RRGGBB hex color, received 'red'`). CLI rejects invalid color before auth.
- **Docs / install**: canonical GitHub repository is [`pipefy/ai-toolkit`](https://github.com/pipefy/ai-toolkit). Install snippets, `install.sh`, MCP setup links, Claude plugin metadata, and `.mcp.json` now point at `github.com/pipefy/ai-toolkit` (GitHub may still redirect older URLs).
- **SDK**: GraphQL `HTTPXAsyncTransport` now sets `verify=True` explicitly to pin TLS verification on, independent of httpx's default.
- **Deps**: upgraded `pydantic` to 2.13.4 (`pydantic-core` 2.46.4, `pydantic-settings` 2.14.1) across workspace packages.
- **Deps**: upgraded `gql[httpx]` to 4.0.0; `gql()` constants are `GraphQLRequest` objects (use `.document` for AST introspection in tests).

## [0.2.0-beta.3] - 2026-06-03

### Fixed

- **SDK / MCP / CLI**: AI automation create and update no longer require service-account credentials. `generate_with_ai` create/update were routed through the `/internal_api` endpoint and gated behind a service-account check, so a normal user session (stored session from `pipefy auth login`, or a `--token` bearer) could not create or update an AI automation, which broke install flows that provision an AI triage automation. Both now go through the public `createAutomation` / `updateAutomation` mutations under the caller's normal auth, matching the read, list, and delete paths. Closes #272.

### Changed

- **SDK**: the AI automation surface moved from `AiAutomationService` to `AutomationService.create_ai_automation` / `update_ai_automation`, mirroring the existing `create_send_task_automation` pattern. `AiAutomationService`, `ai_automation_queries.py`, the `ai_automation_available` property, and `set_ai_automation_service` are removed; `PipefyClient` delegates to `AutomationService`.

## [0.2.0-beta.2] - 2026-06-02

### Added

- **MCP / CLI / SDK**: `get_automation_event_attributes` lists official `field_map.value` tokens; `create_automation` preflights `field_map` destination `fieldId` values (numeric `internal_id` on `action_repo_id`) and `card_moved` + `move_single_card` transitions before GraphQL. Skill and `docs/mcp/tools/automations-and-ai.md` document create-only preflight and text-only move-transition errors (recovery via error message or `get_phase_allowed_move_targets`, not a `valid_destinations` envelope field).
- **Installer**: new POSIX `install.sh` at the repo root. One command installs the CLI + MCP server via `uv tool install` (resolving the latest GitHub Release tag via the GitHub API and discovering the wheel assets directly, no hardcoded package list), optionally adds skills via `npx skills add`, and writes the MCP server registration into the user's chosen client config (Cursor / Claude Desktop / Codex / Claude Code / none-mode print). Flags: `--yes`, `--no-skills`, `--client <id>`, `--version <tag>`, `--prefix <dir>`, `--allow-root`, `--dry-run`, `--help`. After install, `pipefy-mcp-server` is on PATH so client configs collapse to `{"command": "pipefy-mcp-server"}`. shellcheck-clean. Closes #231.
- **SDK / Auth**: shared filesystem-backed configuration via `~/.config/pipefy/config.toml` (`%APPDATA%\pipefy\config.toml` on Windows; honours `XDG_CONFIG_HOME` and a `PIPEFY_CONFIG_FILE=<path>` override). Top-level TOML keys map to pydantic field names on `AuthSettings` and `PipefySettings`; precedence is `init kwargs > env > .env > config.toml > defaults`. The new `pipefy-infra` workspace package owns the loader (a schema-agnostic `PydanticBaseSettingsSource` subclass) and the path-discovery helpers; SDK and Auth depend on it symmetrically — neither imports the other. See [`docs/config.md`](docs/config.md) for the schema.
- **CLI**: `pipefy auth status [--json|-j]` — reports auth source, identity, session expiry, and exit codes.
- **CLI**: `pipefy auth logout` — revokes the refresh token at the IdP and clears the stored session.
- **Auth**: `AuthSettings.auth_url` now defaults to the Pipefy production IdP when `PIPEFY_AUTH_URL` is unset — removes the previous `PIPEFY_AUTH_URL is required` exit-2 friction on `pipefy auth login` / `pipefy auth logout` and wires the MCP stored-session tier automatically after `pipefy auth login`. Override by setting `PIPEFY_AUTH_URL=<url>` to a non-prod IdP. Closes #233.
- **Auth / CLI / MCP**: opt-out for the keychain-backed stored-session tier. `PIPEFY_DISABLE_STORED_SESSION=1` (or `disable_stored_session=true` in `config.toml`) makes `AuthSettings.to_oidc_client()` return `None`: tier resolution skips the keychain entirely (no backend discovery, no `load_session` probe), and `pipefy auth login` / `pipefy auth logout` refuse with exit code 2. `PIPEFY_KEYCHAIN_BACKEND=file` (or `keychain_backend = "file"`) swaps the active `keyring` backend to `keyrings.alt.file.PlaintextKeyring` writing under `~/.config/pipefy/keyring.cfg` (`%APPDATA%\pipefy\keyring.cfg` on Windows). Unblocks headless Linux without Secret Service and CI runners; the file stores credentials in plaintext on disk, so it's opt-in only. Closes #237.
- **SDK / Auth**: introduced `PIPEFY_BASE_URL` (default `https://app.pipefy.com`) that drives the four API endpoints (`graphql_url`, `internal_api_url`, `interfaces_graphql_url`, `service_account_url`) as pydantic `@computed_field` properties. Operators on non-prod environments set `PIPEFY_BASE_URL=<host>` once and all four endpoints follow. The OIDC issuer (`PIPEFY_AUTH_URL`, default `https://signin.pipefy.com/realms/pipefy`) remains a separate full-URL field because non-prod realm names don't follow a derivable convention. Closes #238.
- **MCP**: stored-session tier wired into `ServicesContainer`; setting `PIPEFY_AUTH_URL` after `pipefy auth login` now lets the MCP server reuse the keychain-backed session, with the refresh pre-warmed at startup so a stale or revoked session surfaces before the first tool call.
- **Auth**: reactive refresh-on-401 for the stored-session tier (`RefreshableBearerAuth`). When an API call returns 401, the SDK transport forces a refresh via `ensure_fresh_session(force=True)`, persists any rotated tokens, and retries the request once before surfacing the error. Complements the eager refresh path for IdP-side revocation and mid-process token expiry. Closes #137.

### Changed

- **SDK / MCP / CLI**: renamed the two service-account credential env vars for clarity and to remove the one-letter footgun against `PIPEFY_AUTH_URL` (interactive user-login issuer): `PIPEFY_OAUTH_CLIENT` → `PIPEFY_SERVICE_ACCOUNT_CLIENT_ID`, `PIPEFY_OAUTH_SECRET` → `PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET`. `PIPEFY_OAUTH_URL` is dropped without a renamed counterpart — the OAuth token endpoint now derives from `PIPEFY_BASE_URL` (see the **Removed** section). Closes #127.
- **MCP / CLI**: attachment uploads accept `file_path` only (local filesystem path, with `~` expansion). `file_url` and `file_content_base64` are both gone — the MCP server runs as a local subprocess of the user's agent runtime, so any path the user can read is a valid source, and agents that hold generated bytes write them to a temp file and pass the path. `file_name` is optional (basename inferred from the path). The SDK exposes a single `client.upload_attachment(attachment, organization_id=..., target=...)` method backed by `AttachmentService.upload_attachment`, which owns the full choreography (file read → presigned URL → S3 PUT → field update) and enforces the 100 MiB cap as part of its internal `LocalFile.read`. Per-step wire helpers (`create_presigned_url`, `upload_file_to_s3`, `extract_storage_path`) are private to `AttachmentService`; the S3 PUT step is dispatched via an injectable `S3Uploader` protocol (`HttpxS3Uploader` is the default). Domain types: `pipefy_sdk.Attachment` (path-based, no upload methods), `CardTarget` / `TableRecordTarget` value objects, plus the `AttachmentUploadError` / `AttachmentUploadResult` / `AttachmentUploadStep` types previously in `attachment_upload`. See `packages/mcp/AGENTS.md` for the `GATED:SELF_HOSTED` convention that marks where URL ingestion would return under a future self-hosted profile.
- **Infra**: `pipefy_infra.security` widens the literal-IP / DNS-result blocklist to include multicast (`224.0.0.0/4`), reserved (`240.0.0.0/4`), and unspecified (`0.0.0.0`, `::`) ranges in addition to the prior private / loopback / link-local set. Error messages updated to enumerate the blocked categories explicitly. The widening relies on stdlib `ipaddress.IPv4Address.is_*` / `IPv6Address.is_*` properties so IPv4-mapped IPv6 literals (`::ffff:127.0.0.1`) are also covered.
- **Infra**: `security.validate_https_url` and `security.assert_url_is_host_root` no longer take a `derived_paths_hint` parameter. Callers wrap the `ValueError` with their own caller-specific context if needed; the helpers stay caller-agnostic.
- **Auth**: `PIPEFY_KEYCHAIN_BACKEND` env / TOML values are now normalized with `.strip().lower()` so `AUTO`, ` File `, etc. match the `Literal["auto", "file"]` constraint instead of failing with a cryptic Literal-validation error. Previous behavior accepted only the exact lower-case spelling.
- **Auth**: `PIPEFY_AUTH_URL` now rejects query strings and fragments (path is allowed for Keycloak-style realm URLs). Previously, only `validate_https_url`'s scheme + literal-IP check ran on `auth_url`, so a stray `?` or `#` from operator copy-paste would pass settings construction and corrupt the downstream `.well-known/openid-configuration` concatenation.
- **Infra**: `security.assert_url_is_host_root` rejects repeated-slash paths (`//`, `///`) that the previous inline `path.strip('/')` check accepted. Deploy configs with `PIPEFY_BASE_URL=https://app.pipefy.com//` (extra slash) now fail at startup; trim to a single trailing slash or none.
- **Infra**: `security.assert_hostname_resolves_to_public_ips` raises `ValueError` instead of silently passing when `socket.getaddrinfo` returns an empty address list. `UnicodeError` from IDN encoding (e.g. labels > 63 chars) is now caught alongside `socket.gaierror` and surfaced as a `ValueError` with the same `Could not resolve hostname` shape.
- **Auth / SDK**: every `PIPEFY_*` env var is validated against a semantically meaningful pattern at settings construction. URL env vars (`PIPEFY_BASE_URL`, `PIPEFY_AUTH_URL`) require `https?://` plus non-whitespace; credential fields (`PIPEFY_TOKEN`, `PIPEFY_SERVICE_ACCOUNT_CLIENT_ID`, `PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET`, `PIPEFY_AUTH_CLIENT_ID`) reject leading / trailing whitespace; `PIPEFY_ORG_ID` must be an ASCII numeric string. There is no longer an empty-string opt-out for any tier — unset the variable to fall back to the default, or use `PIPEFY_DISABLE_STORED_SESSION=1` to turn the stored-session tier off explicitly (see the **Added** entry above).
- **SDK / MCP / CLI**: renamed `--graphql-url` CLI flag to `--base-url` to match the new env-var shape.
- **Install snippets**: every `git+https://github.com/gbrlcustodio/pipefy-mcp-server` URL in the root `README.md`, `packages/mcp/README.md`, `packages/cli/README.md`, the shipping `.mcp.json`, and `commands/install.md` now pins `@latest` — a moving git tag the release flow updates to point at the most recent release. Users get release-stable installs by default; `@v0.2.0-beta.1`-style pins remain available for reproducibility. The release process documented in `RELEASE.md` now includes `git tag -f latest <version> && git push --force-with-lease origin latest` as the step that rolls new installs forward.

### Deprecated

- **SDK**: legacy `PIPEFY_OAUTH_*` env vars still resolve to the new `service_account_*` fields via an alias shim, with a one-shot stderr deprecation warning per legacy key. The aliases will be removed in a later `0.2.0-beta.x` release (carrying an explicit breaking-change callout). See [`docs/MIGRATION.md`](docs/MIGRATION.md#service-account-env-var-rename).

### Fixed

- **SDK**: portal Interfaces helpers map `TransportQueryError` to `PortalPermissionError` only when GraphQL `extensions.code` is `PERMISSION_DENIED`. Other Interfaces failures (validation, not found, etc.) now propagate as `TransportQueryError` instead of being mislabeled as permission errors. SDK callers that caught `PortalPermissionError` for all portal GraphQL errors should also handle `TransportQueryError`.
- **CLI**: concurrent `pipefy` invocations near token expiry no longer surface `invalid_grant` errors; the refresh-token grant is now serialized across processes via a filesystem lock at `~/.config/pipefy/refresh.lock` (`%APPDATA%/pipefy/refresh.lock` on Windows). Closes #133.
- **Installer**: `install.sh` now prefers the system `python3` on macOS when bootstrapping `uv tool` venvs, fixing installs on stock macOS where Homebrew Python is not on PATH. (#267)

### Removed

- **Docs**: `docs/setup.md` deleted. Per-client MCP wiring (Cursor, Claude Desktop, Claude Code including the `/pipefy:install` + `/pipefy:login` plugin sequence, Codex) now lives in the root `README.md#installation`. `PIPEFY_*` environment variables, validation rules, and the legacy-alias notes move to a new `## Environment variables` section in [`docs/config.md`](docs/config.md). Edge cases (`errSecParam (-25244)` macOS keychain note, `.mcp.json` variants, local-clone alternative, `claude mcp add` form) move to [`packages/mcp/README.md`](packages/mcp/README.md). CLI auth tier breakdown moves to [`packages/cli/README.md`](packages/cli/README.md). Closes #246.
- **Tooling**: `bootstrap.sh` removed. The equivalent (`uv sync` + `cp .env.example .env`) is inlined into the `## Development` section of the root `README.md`.
- **HARD BREAK** — per-URL env vars dropped in favor of `PIPEFY_BASE_URL` + `PIPEFY_AUTH_URL`. The following env vars are no longer recognized; `PipefySettings` / `AuthSettings` are configured with `extra="ignore"`, so settings construction silently drops them with no exception or warning — stale `.env` keys look configured but the prod defaults still apply. Same wording as `docs/MIGRATION.md`. Audit `.env`, MCP client JSON, and CI secrets before upgrading:
  - `PIPEFY_GRAPHQL_URL` — set `PIPEFY_BASE_URL` to your API host (graphql_url derives as `<base>/graphql`).
  - `PIPEFY_INTERNAL_API_URL` — derives as `<base>/internal_api`.
  - `PIPEFY_INTERFACES_GRAPHQL_URL` — derives as `<base>/graphql/interfaces`.
  - `PIPEFY_SERVICE_ACCOUNT_URL` — derives as `<base>/oauth/token`.
  - `PIPEFY_OAUTH_URL` (legacy alias for `PIPEFY_SERVICE_ACCOUNT_URL`) — no replacement; same derivation path.

  Migration: replace the five per-URL env vars with a single `PIPEFY_BASE_URL` (default `https://app.pipefy.com`). If you need a non-prod OIDC issuer, also set `PIPEFY_AUTH_URL` to the full issuer URL.
- `PIPEFY_TENANT` / `PIPEFY_AUTH_REALM` env vars (never shipped in a release; existed only on intermediate commits of this branch).
- **Auth**: `pipefy_auth.DEFAULT_AUTH_URL` constant (and its re-export from the package root). Callers should consult the resolved `AuthSettings.auth_url` instead.
- **CLI**: `pipefy skills list` / `pipefy skills show` Typer subcommands and the bundled `packages/cli/src/pipefy_cli/skills/*.md` starter pack. Install the full catalog via [`skills.sh`](https://github.com/vercel-labs/skills) (`npx skills add gbrlcustodio/pipefy-mcp-server`) or reference the canonical files under `skills/<domain>/<skill>/SKILL.md` directly. Closes #230.
- **Tooling**: `scripts/sync_starter_pack.py` (canonical files at `skills/<domain>/<skill>/SKILL.md` are now the only source).
- **CLI**: `pyyaml` dependency of `pipefy-cli` (only consumer was the deleted `skills` command).
- **SDK**: dropped the `pipefy_sdk.utils.url_ssrf` module and its `pipefy_sdk.utils` re-exports. The shared implementation now lives in `pipefy_infra.security`; import the module (`from pipefy_infra import security`) and call through it (`security.validate_https_url(...)`).
- **Auth / SDK**: the per-module `_URL_SHAPE_PATTERN` regex literals in `pipefy_auth.settings` and `pipefy_sdk.settings` are gone; both modules now reference `pipefy_infra.security.URL_SHAPE_PATTERN`. The `_strip_str` validator body stays inlined as a 2-line classmethod on each model (no shared helper).
- **Infra**: `pipefy_infra` no longer re-exports symbols at the package root; the root exposes only `__version__`. Submodules: `pipefy_infra.config` (Pipefy on-disk configuration: path discovery + TOML source) and `pipefy_infra.security` (SSRF defenses: shape pattern + internal-IP gate + DNS-rebinding gate). The `security` module is the SSRF audit namespace: import the module and call through it so every call site is greppable via `security.` (same idiom as stdlib `hmac.compare_digest`, `secrets.token_urlsafe`).
- **MCP**: dropped URL ingestion (`file_url`, `_validate_url_safe`, redirect loop, download size cap) and base64 ingestion (`file_content_base64`) from attachment uploads. The MCP server runs as a local subprocess of the agent runtime, so the only attachment source is `file_path`; agents that generated bytes write them to a temp file and pass the path. The SSRF defenses are recorded as `GATED:SELF_HOSTED` in `packages/mcp/src/pipefy_mcp/tools/attachment_tools.py`; bring them back behind a capability flag if a hosted MCP profile is added. The shared `pipefy_infra.security.validate_and_assert_public_url` helper stays, used by `base_url` / `auth_url` validation. See `packages/mcp/AGENTS.md` for the `GATED:<PROFILE>` convention.

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
