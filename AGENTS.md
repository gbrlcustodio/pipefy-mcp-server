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

How `PIPEFY_*` env vars, `.env`, and `config.toml` become typed inputs. The operator-facing contract (every var, the precedence chain, the TOML schema) lives in `docs/config.md`; this section is the internal design contract. The model is "parse, don't validate": raw text is parsed once, at the edge, into refined value objects that the rest of the system trusts by construction.

### The parse pipeline

Configuration flows through one directional pipeline, each stage discarding the looser representation behind it:

```
raw env / .env / toml
  -> [string parse: strip / fold / coerce / precedence]   readers in pipefy_*/env.py
  -> [projection parse: wide reader -> value object]       loaders in pipefy_*/env.py
  -> refined value objects (the API surface)               PipefyEndpoints, ServiceAccount, ...
  -> behavior                                              PipefyClient, resolve_pipefy_auth, JwtValidator
```

A reader is a `pydantic_settings.BaseSettings` shell that knows the env mapping; a loader is a function that reads one reader, projects it onto a refined value object, and returns that object plus primitives. Both are transient scaffolding: the application holds the loader's output, never the reader.

### Public APIs take refined value objects, never a config instance

A library's public entry point accepts only refined value objects (a frozen `pydantic.BaseModel` whose construction witnesses validity) and primitives. `PipefyClient(endpoints: PipefyEndpoints, *, auth, allow_insecure_urls, ...)`, `resolve_pipefy_auth(sources: CredentialSources)`, and `JwtValidator(inputs: JwtValidationInputs)` are the shape: a caller cannot hand them a half-validated reader. No library public `__init__` exports a `*Config` / `*Settings` symbol, and no `*Config` appears in one of these signatures (a greppable guard in the chore commit enforces both). Construction of the value object is the single validation gate, so every path that builds one (the loader, a test, a future caller) gets the same checks.

### Shape rides the value object; posture policy parses at the deployment edge

Two distinct parses, kept separate because they need different context:

- **Shape** is context-free and rides every construction path: URL shape (`security.URL_SHAPE_PATTERN`), no query/fragment, `OPAQUE_CREDENTIAL_PATTERN` on credentials, and cross-field rules (`verify_audience => audience`). It lives on the value object (a field `pattern=` plus a `model_validator(mode="after")`), so a hand-built object cannot be malformed.
- **Posture policy** is context-dependent (`validate_https_url(allow_insecure=...)`, blocked IP ranges) and parses once at the deployment edge. `pipefy_infra.deployment.DeploymentConfig` gates `base_url` as a host root, which covers every derived suffix (`graphql_url`, `oauth_token_url`, ...); its derived URLs are then witnesses that the policy parse passed. There is one source of `allow_insecure_urls` (the one `DeploymentConfig`), so endpoints, the service-account `token_url`, and the inbound issuer cannot diverge on host or posture.

### Parsers live in per-package env.py submodules

Each library that reads env owns one `env.py`: `pipefy_infra.env` (`load_deployment`), `pipefy_sdk.env` (`load_sdk`), `pipefy_auth.env` (`load_auth`, `load_jwt_validation`). These are the only modules allowed to import `pydantic_settings`; a per-package ruff `banned-api` rule bans it everywhere else, with a per-file exception for `env.py` and for `infra/settings_base.py`. The env-reading dependency is an optional extra (`pipefy-sdk[env]`, `pipefy-auth[env]`), so `import pipefy_sdk` / `import pipefy_auth` pulls no `pydantic_settings`. The two application composition roots (`pipefy_cli.runtime.resolve_cli_runtime`, `pipefy_mcp.runtime.resolve_mcp_runtime`) compose the loaders around one `DeploymentConfig`; they never redefine the env mapping. The resolved composite each app holds is a `*Runtime` (`CliRuntime`, `McpRuntime`) of parsed value objects and primitives, not a bag of readers.

### PipefyBaseSettings owns the source chain

Each reader subclasses `pipefy_infra.settings_base.PipefyBaseSettings`, which owns the one precedence chain (init > env > dotenv > `config.toml` > file secret) and the shared `SettingsConfigDict`. A reader therefore adds only its `env_prefix`, any cross-prefix `validation_alias` (for example `PIPEFY_TOKEN`, kept at the product root), and `_toml_section`. `PipefyBaseSettings` is generic machinery (imports only `pydantic_settings` and the TOML source), so `infra` stays a leaf.

Normalizing human-typed input is the reader's job, not the value object's. Whitespace trimming is uniform, so it is a single wildcard `field_validator("*", mode="before")(strip_if_str)` on `PipefyBaseSettings` that trims every value as it is read. Field-specific leniency (case-folding `keychain_backend`, where `KEYCHAIN_BACKEND=FILE` folds to `file`) cannot ride the blanket wildcard, since most fields are case-sensitive; the reader wires it onto the field with `field_validator("keychain_backend", mode="before")(lower_if_str)`. The value objects do NOT normalize: a credential or URL `pattern=` excludes surrounding whitespace, and a padded or mixed-case value passed to a value object directly is a programmer error that raises. Tests assert the layering: readers strip and fold env input; direct construction with a non-canonical value raises.

### Sectioned TOML

When the same bare field name appears across concepts (`issuer_url` lives in both `[auth]` and `[jwt]`), the reader sets `_toml_section` so `PipefyTomlConfigSource` reads from that sub-table instead of the top level. Credentials stay at the product root (`PIPEFY_TOKEN`, `PIPEFY_SERVICE_ACCOUNT_*`); the login subsystem is namespaced under `PIPEFY_AUTH_*`.

### Lazy resolution (MCP)

Importing `pipefy_mcp.runtime` does no env or file IO. `get_runtime()` resolves and caches on first call; `reset_runtime()` clears the cache and an autouse test fixture calls it so the process-wide cache does not leak across tests.

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
