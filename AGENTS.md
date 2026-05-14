# Repository Guidelines

## Documentation map
- **`README.md`** — Project pitch, install commands (pre-launch git + post-v1.0 PyPI), repo layout, MCP tools table, skills section, contributing.
- **`docs/setup.md`** — First-time install, env vars, MCP client config.
- **`docs/parity.md`** — MCP tool ↔ CLI command parity matrix. Source of truth for coverage and deferrals.
- **`docs/MIGRATION.md`** — What existing MCP users need to know about v0.1.
- **`docs/dependencies.md`** — Rationale for runtime dependencies.
- **`docs/tools/`** — Per-area reference (parameters, edge cases, cross-cutting behavior).
- **`skills/AGENTS.md`** — Skill-authoring guide (frontmatter, naming, style). Start here before adding a skill.

## Project structure

```
packages/sdk/   → pipefy-sdk        (Vendor API SDK — GraphQL, models, services)
packages/mcp/   → pipefy-mcp-server (MCP tools, server lifecycle; depends on pipefy-sdk)
packages/cli/   → pipefy-cli        (Typer CLI; depends on pipefy-sdk)
skills/         → agent skills catalog (Markdown; no Python package)
```

See [ADR 0003](.cursor/dev-planning/specs/pipefy-labs/decisions/0003-monorepo-package-taxonomy.md) for the canonical vocabulary (why "Vendor API SDK" and not "shared"/"core").

## Build, test, and development

- `uv sync` — install all workspace members.
- `uv run pipefy-mcp-server` — run MCP server locally.
- `uv run pipefy --help` — run CLI locally.
- `uv run pytest` — full test suite.
- `uv run ruff check .` / `uv run ruff format .` — lint and format.
- Coverage: `uv run pytest --cov=packages/sdk/src/pipefy_sdk --cov-report=term-missing`.

### Manual E2E
Use **Cursor's MCP integration** as the primary smoke test for tool changes. MCP Inspector (`npx @modelcontextprotocol/inspector uv --directory . run pipefy-mcp-server`) is fine for protocol debugging.

## Coding style
- Python 3.11+ with `from __future__ import annotations` on every module.
- Built-in generics (`list[str]`, `dict[str, Any]`), union syntax (`str | None`).
- `ruff` enforces formatting and import sorting — run before committing.

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

**Same-PR rule:** breaking command renames must update affected skills in the same PR (or a paired PR opened in the same review window). CI (`skills-lint.yml`) validates every skill reference against the CLI and MCP registry — a rename without a skill update fails the build.

## Commit & PR guidelines
- Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:` with optional scopes.
- One functional change per commit (atomic). PRs touching more than 10 files or 300 changed lines should be split.
- PRs must include: summary, testing performed (commands + results), docs updates if tool behavior or config changed.

## Security
- Credentials via env vars or `.env`; never commit secrets.
- GraphQL schema updates: `uv run gql-cli ...` → update `packages/sdk/tests/services/pipefy/schema.graphql`; see README schema hygiene checklist.
