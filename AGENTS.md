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
packages/sdk/   → pipefy-sdk        (Vendor API SDK — GraphQL, models, services)
packages/mcp/   → pipefy-mcp-server (MCP tools, server lifecycle; depends on pipefy-sdk)
packages/cli/   → pipefy-cli        (Typer CLI; depends on pipefy-sdk)
skills/         → agent skills catalog (Markdown; no Python package)
```

**Vendor API SDK** means the GraphQL-facing library (`pipefy-sdk`) used by both MCP and CLI, distinct from app glue or generic shared helpers.

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
- A `dict`-typed tool arg (for example `filter: dict | None`) validates the container but not its nested values. Validating that nested, un-schema'd structure (the job of `validate_report_cards_filter`) is legitimate boundary work, not defensive noise.

When a type-related failure looks plausible, the fix is a type checker in CI, not a per-function guard.

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
