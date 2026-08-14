# Repository Guidelines

## Documentation map
- **`README.md`**. Project pitch, one-page install front door (`README.md#installation`: hosted MCP, Quick install, Claude Code plugin, CLI, skills), repo layout, MCP tools table, contributing.
- **`CONTRIBUTING.md`**. Skills contribution guide (frontmatter, CI, style). The entry point for GitHub contributors.
- **`docs/README.md`**. Index of docs by application (MCP, CLI, SDK) and shared guides.
- **`docs/config.md`**. `PIPEFY_*` environment variables, `config.toml` schema, precedence chain.
- **`docs/parity.md`**. MCP tool ↔ CLI command parity matrix. Source of truth for coverage and deferrals.
- **`docs/MIGRATION.md`**. What existing MCP users need to know about v0.1.
- **`docs/contributing/dependencies.md`**. Rationale for runtime dependencies.
- **`docs/uninstall.md`**. `uninstall.sh --scan` and teardown, and switching between the hosted, local, and plugin channels. The two root scripts are colocated so `install.sh` and `uninstall.sh` stay reviewable side by side. A test asserts every file the installer writes is one the teardown accounts for.
- **`docs/contributing/architecture.md`**. The map of the architecture. The quality requirements and the constraints that shape it, the boundary with its diagram, and the decomposition into applications, packages, and layers. Then the tool surface, the response shape, one runtime scenario, the rules that cross every package, the known debt, and the glossary.
- **`docs/contributing/conventions.md`**. The code conventions, as rules with permanent IDs. A rule belongs there when a reviewer applies it by judgment to one unit of code.
- **`docs/mcp/tools/`**. Per-area MCP tool reference (parameters, edge cases, cross-cutting behavior). Includes `identifiers.md`, the canonical map of which tool/argument expects slug vs `internal_id` vs uuid vs numeric id.
- **`docs/cli/`**. CLI-specific guides, for example introspect-then-execute.
- **`docs/sdk/README.md`**. Using `pipefy` as a library.
- **`skills/AGENTS.md`**. Skill-authoring guide (frontmatter, naming, style). Start here before adding a skill.
- **`skills/onboarding/pipefy-toolkit-setup/`**. First-time setup checklist for agents. It links to README snippets and owns no commands.

## Project structure

```
packages/sdk/   → pipefy            (Vendor API SDK: GraphQL, models, services. Dist named `pipefy`, import module `pipefy_sdk`)
packages/mcp/   → pipefy-mcp-server (MCP tools, server lifecycle. Depends on pipefy)
packages/cli/   → pipefy-cli        (Typer CLI. Depends on pipefy)
packages/auth/  → pipefy-auth       (Shared OAuth and keychain helpers for CLI and MCP. Depends on pipefy-infra)
packages/infra/ → pipefy-infra      (Shared TOML config loader, path discovery, SSRF defenses, string helpers. Leaf package)
skills/         → agent skills catalog (Markdown, no Python package)
```

**Vendor API SDK** means the GraphQL-facing library (`pipefy`) used by both MCP and CLI, distinct from app glue or generic shared helpers.

## Import namespace migration: `pipefy_sdk` → `pipefy`

The SDK distribution is named `pipefy`, but its import module is still `pipefy_sdk`. The
import module is being renamed to `pipefy` gradually, so the distribution and import names
converge. New code should target `pipefy`; existing `pipefy_sdk` imports are migrated in
small batches rather than one sweep.

The mechanism that lets both paths work during the transition is a `sys.modules` alias. The
real code lives at the new location and the old name is aliased to the *same module object*,
so `import pipefy_sdk` keeps resolving. Once code moves under a `pipefy/` package:

```python
# src/pipefy_sdk/__init__.py (transitional shim)
import sys

import pipefy as _pipefy

sys.modules[__name__] = _pipefy
```

Rules for the migration:

- Do NOT shim with `from pipefy import *`. That re-imports and creates two copies of every
  class under two names, which breaks `isinstance` checks and module-level singletons. The
  `sys.modules` alias preserves a single module identity; use it.
- Migrate call sites incrementally. New code imports `pipefy`; touch old `pipefy_sdk` imports
  as you pass through their files.
- Add a lint/grep guard so new `pipefy_sdk` imports fail once the migration starts, so the old
  surface only ever shrinks.
- On completion: remove the shim, repoint the ruff banned-api paths (`pipefy_sdk.services`,
  `pipefy_sdk.queries` → `pipefy.services`/`.queries`), move `__version__` into
  `pipefy/__init__.py`, and rename the directory `packages/sdk` → `packages/pipefy`.

## Build, test, and development

- `uv sync` — install all workspace members.
- `uv run pipefy-mcp-server` — run MCP server locally.
- `uv run pipefy --help` — run CLI locally.
- `uv run pytest` — full test suite.
- `uv run ruff check .` / `uv run ruff format .` — lint and format.
- `uvx pre-commit install` — opt in to the ruff lint + format git hook (one-time, per clone). Run against the whole tree with `uvx pre-commit run --all-files`; bypass for a WIP commit with `git commit --no-verify`. The hook's ruff `rev` in `.pre-commit-config.yaml` must move with `uv.lock` to keep hook and CI aligned.
- Shell scripts (`install.sh`, `uninstall.sh`) are covered by the same hook file: `shellcheck --shell=sh` from `shellcheck-py` (a Python package, so no Docker), `sh -n`, and a check that every `rm` / `rmdir` in `uninstall.sh` routes through its `remove_path` guard. CI runs the same three plus `dash -n`, and pins the same `shellcheck-py` release the hook does.
- Coverage: `uv run pytest --cov=packages/sdk/src/pipefy_sdk --cov-report=term-missing`.

### Manual E2E
Use **Cursor's MCP integration** as the primary smoke test for tool changes. MCP Inspector (`npx @modelcontextprotocol/inspector uv --directory . run pipefy-mcp-server`) is fine for protocol debugging.

## Coding style
- Python 3.11+ with `from __future__ import annotations` on every module.
- Built-in generics (`list[str]`, `dict[str, Any]`), union syntax (`str | None`).
- `ruff` enforces formatting and import sorting — run before committing.

### Coding principles

The code conventions live in [`docs/contributing/conventions.md`](docs/contributing/conventions.md). A rule belongs there when a reviewer applies it by judgment to one unit of code, from validating at the edge to when we lift a constraint we imposed on ourselves. Each rule carries a permanent ID, so cite the ID (`PARSE-3`) rather than quoting the text.

The map of the architecture lives in [`docs/contributing/architecture.md`](docs/contributing/architecture.md): the quality requirements it serves, the constraints it accepts, and the boundary it draws. It decomposes the code into applications, packages, and layers, states the rules that cross every package, and carries one runtime scenario. It also lists where the code does not match that map, and settles the names that carry a second meaning. Import-linter enforces the intra-package layering in `packages/mcp`, and ruff `TID251` enforces the inter-package direction.

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
4. Register the MCP tool in `packages/mcp/src/pipefy_mcp/tools/`, add its name to `PIPEFY_TOOL_NAMES` in `registry.py`, and assign it a subject domain in `tools/toolsets.py` (the drift-guard in `tests/tools/test_toolsets.py` fails the build for an unassigned tool).
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
