# Repository Guidelines

## Documentation map
- **`README.md`** — Project pitch, one-page install (MCP client JSON for Claude Code / Cursor / Claude Desktop / Codex, CLI, skills), repo layout, MCP tools table, contributing.
- **`CONTRIBUTING.md`** — Skills contribution guide (frontmatter, CI, style); entry point for GitHub contributors.
- **`docs/README.md`** — Index of docs by surface (MCP, CLI, SDK) and shared guides.
- **`docs/config.md`** — `PIPEFY_*` environment variables, `config.toml` schema, precedence chain.
- **`docs/parity.md`** — MCP tool ↔ CLI command parity matrix. Source of truth for coverage and deferrals.
- **`docs/MIGRATION.md`** — What existing MCP users need to know about v0.1.
- **`docs/dependencies.md`** — Rationale for runtime dependencies.
- **`docs/mcp/tools/`** — Per-area MCP tool reference (parameters, edge cases, cross-cutting behavior).
- **`docs/cli/`** — CLI-specific guides (e.g. introspect-then-execute).
- **`docs/sdk/README.md`** — Using `pipefy-sdk` as a library.
- **`skills/AGENTS.md`** — Skill-authoring guide (frontmatter, naming, style). Start here before adding a skill.

## Project structure

```
packages/infra/ → pipefy-infra      (leaf shared helpers: DeploymentConfig, settings base, security, coerce)
packages/sdk/   → pipefy-sdk        (Vendor API SDK: GraphQL, models, services; depends on pipefy-infra)
packages/auth/  → pipefy-auth       (auth value objects + resolver; depends on pipefy-infra)
packages/mcp/   → pipefy-mcp-server (MCP tools, server lifecycle; depends on pipefy-sdk + pipefy-auth)
packages/cli/   → pipefy-cli        (Typer CLI; depends on pipefy-sdk + pipefy-auth)
skills/         → agent skills catalog (Markdown; no Python package)
```

**Vendor API SDK** means the GraphQL-facing library (`pipefy-sdk`) used by both MCP and CLI, distinct from app glue or generic shared helpers.

Dependency direction is strict and one-way: `infra` is a leaf (imports only third-party + its own modules), `sdk` and `auth` build on `infra` and never import each other, and the applications (`mcp`, `cli`) sit on top. Per-package ruff `flake8-tidy-imports.banned-api` rules enforce these edges, so a forbidden upward or sideways import fails lint.

## Build, test, and development

- `uv sync` — install all workspace members.
- `uv run pipefy-mcp-server` — run MCP server locally.
- `uv run pipefy --help` — run CLI locally.
- `uv run pytest` — full test suite.
- `uv run ruff check .` / `uv run ruff format .` — lint and format.
- `uvx pre-commit install` — opt in to the ruff lint + format git hook (one-time, per clone). Run against the whole tree with `uvx pre-commit run --all-files`; bypass for a WIP commit with `git commit --no-verify`. The hook's ruff `rev` in `.pre-commit-config.yaml` must move with `uv.lock` to keep hook and CI aligned.
- Coverage: `uv run pytest --cov=packages/sdk/src/pipefy_sdk --cov-report=term-missing`.

### Manual E2E
Use **Cursor's MCP integration** as the primary smoke test for tool changes. MCP Inspector (`npx @modelcontextprotocol/inspector uv --directory . run pipefy-mcp-server`) is fine for protocol debugging.

## Coding style
- Python 3.11+ with `from __future__ import annotations` on every module.
- Built-in generics (`list[str]`, `dict[str, Any]`), union syntax (`str | None`).
- `ruff` enforces formatting and import sorting — run before committing.

### Type validation at boundaries, not inside

Static typing is the contract for internal code; do not re-check it at runtime. A parameter annotated `value: str` is trusted by every internal caller, and a type checker, not a hand-written `isinstance` guard, is the right place to enforce it. Adding runtime type guards inside internal functions reinvents dynamic typing by hand and sets the wrong norm: do it once and it becomes the expectation everywhere.

Runtime type checks belong only at a trust boundary, where untyped or external data crosses into typed code and static analysis cannot follow:

- The MCP tool signature is the boundary. FastMCP is pydantic-backed, so a scalar arg declared `color: str` is coerced and rejected there. SDK planners called behind it (for example `normalize_label_color`) trust the type and must not guard it again.
- The CLI command signature is the same kind of boundary. Typer parses and coerces options against their annotations (a `color: str` option in `pipefy_cli` is the rejection point), and the same SDK planners run behind it, so the MCP and CLI surfaces validate at the edge and trust the type underneath identically.
- A `dict`-typed tool arg (for example `filter: dict | None`) validates the container but not its nested values. Validating that nested, un-schema'd structure (the job of `validate_report_cards_filter`) is legitimate boundary work, not defensive noise.

When a type-related failure looks plausible, the fix is a type checker in CI, not a per-function guard.

## Settings and configuration architecture

How `PIPEFY_*` env vars, `.env`, and `config.toml` become typed config. The operator-facing contract (every var, the precedence chain, the TOML schema) lives in `docs/config.md`; this section is the internal design contract.

### Library / application split

The library packages (`infra`, `sdk`, `auth`) are pure `pydantic.BaseModel` value objects: they validate themselves but read no env or file. Reading the environment is an application concern owned by exactly one composition root per app: `pipefy_cli.config.resolve_cli_settings` and `pipefy_mcp.settings.resolve_mcp_settings`. Libraries MUST NOT import `pydantic_settings` (a per-package ruff rule enforces it). New config knobs are declared as fields on the relevant library value object, and the edge reads them; do not add a second env-reading path.

### One DeploymentConfig, injected by reference

`pipefy_infra.deployment.DeploymentConfig` is the single source of host topology (`base_url` plus the derived `graphql_url` / `internal_api_url` / `interfaces_graphql_url` / `oauth_token_url` properties) and the single SSRF posture (`allow_insecure_urls`). The composition root builds ONE instance and injects it by reference into the SDK / auth / jwt / resource-server configs, so they cannot structurally diverge on host or posture. Injected fields (`deployment`, `service_account`) are required (no default) on the library models, so the type system forces the edge to supply them. Models that hold a `deployment` forward `allow_insecure_urls` (and the SDK its URL properties) off it rather than storing their own copy.

### PipefyBaseSettings owns the source chain

Each edge reader subclasses its library model plus `pipefy_infra.settings_base.PipefyBaseSettings`, which owns the one precedence chain (init > env > dotenv > `config.toml` > file secret) and the shared `SettingsConfigDict`. A reader shell therefore adds only its `env_prefix`, any cross-prefix `validation_alias` (for example `PIPEFY_TOKEN`, kept at the product root), and `_toml_section`. `PipefyBaseSettings` is generic machinery (imports only `pydantic_settings` and the TOML source), so `infra` stays a leaf.

### Normalize at the boundary, validate in the value object

Trimming surrounding whitespace off settings values is a boundary concern: a single wildcard `field_validator("*", mode="before")(strip_if_str)` on `PipefyBaseSettings` trims every value as it is read (env, `.env`, TOML). The library value objects do NOT normalize: they validate and reject a padded value as a programmer error (credential and URL fields carry a `pattern=` that excludes leading/trailing whitespace). Do not add per-field `strip_if_str` validators to library models, and do not re-strip a value inside a `model_validator`. The lone deliberate exception is enum case-folding (for example `AuthConfig.keychain_backend` lower-cases its `Literal`), which is a semantic value-object concern distinct from whitespace hygiene. Tests assert the layering: edge readers strip env input; direct construction of a library model with a padded value raises.

### SSRF gating at construction

URL *shape* is a field-level constraint (`security.URL_SHAPE_PATTERN`); URL *policy* (HTTPS-or-insecure, blocked IP ranges, host-root vs no-query/fragment) runs in a `model_validator(mode="after")` using the injected `allow_insecure_urls`. `DeploymentConfig` gates `base_url` as a host root, which covers every derived suffix; `AuthConfig` gates `issuer_url`, `JwtValidationConfig` gates `issuer_url` + `jwks_uri`, and `ResourceServerSettings` gates `resource_server_url`. There is one source of `allow_insecure_urls` (the injected `DeploymentConfig`); no reader re-reads `PIPEFY_ALLOW_INSECURE_URLS`.

### Sectioned TOML

When the same bare field name appears across concepts (`issuer_url` lives in both `[auth]` and `[jwt]`), the reader sets `_toml_section` so `PipefyTomlConfigSource` reads from that sub-table instead of the top level. Credentials stay at the product root (`PIPEFY_TOKEN`, `PIPEFY_SERVICE_ACCOUNT_*`); the login subsystem is namespaced under `PIPEFY_AUTH_*`.

### Lazy resolution (MCP)

Importing the settings module does no env or file IO. `pipefy_mcp.settings.get_settings()` resolves and caches on first call; `reset_settings()` clears the cache and an autouse test fixture calls it so the process-wide cache does not leak across tests.

## Testing
- `pytest-asyncio`, `pytest-cov`, `pytest-mock`.
- Unit tests: default (no marker needed). Integration tests: `@pytest.mark.integration` (needs `PIPEFY_*` credentials).
- Tests live alongside their package: `packages/<pkg>/tests/`.
- Run a single package: `uv run pytest packages/sdk/tests`.
- CI-style (no network): `uv run pytest -m "not integration"`.

## Adding a New Capability

A capability means an SDK method + MCP tool + CLI command, all in parity:

1. Add the GraphQL query in `packages/sdk/src/pipefy_sdk/queries/`.
2. Add the service method in `packages/sdk/src/pipefy_sdk/services/`.
3. Expose via `PipefyClient` in `packages/sdk/src/pipefy_sdk/client.py`.
4. Register the MCP tool in `packages/mcp/src/pipefy_mcp/tools/` and add its name to `PIPEFY_TOOL_NAMES` in `registry.py`.
5. Add the CLI command in `packages/cli/src/pipefy_cli/commands/` and register it in `main.py`.
6. Update `docs/parity.md` — mark as shipped.
7. Update affected skills in `skills/` in the same PR (or a paired PR in the same review window).

TDD-first: write tests before each layer (red → green → refactor).

## Skills coupling

Skills (`skills/`) and tools (`packages/mcp/`, `packages/cli/`) live in the same monorepo. See **`skills/AGENTS.md`** for the skill-authoring guide.

**Same-PR rule:** breaking command renames must update affected skills in the same PR (or a paired PR opened in the same review window). CI (`skills-lint.yml`) validates `SKILL.md` frontmatter, MCP tool names, and `pipefy` CLI subcommands referenced in `skills/**/SKILL.md` — a rename without a skill update fails the build.

## Commit & PR guidelines
- Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:` with optional scopes.
- One functional change per commit (atomic). PRs touching more than 10 files or 300 changed lines should be split.
- PRs must include: summary, testing performed (commands + results), docs updates if tool behavior or config changed.

## Security
- Credentials via env vars or `.env`; never commit secrets.
- GraphQL schema updates: `uv run gql-cli ...` → update `packages/sdk/tests/services/pipefy/schema.graphql`; see README schema hygiene checklist.
