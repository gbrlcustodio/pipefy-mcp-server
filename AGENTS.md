# Repository Guidelines

## Documentation map
- **`README.md`** — Project pitch, one-page install front door (`README.md#installation`: hosted MCP, Quick install, Claude Code plugin, CLI, skills), repo layout, MCP tools table, contributing.
- **`CONTRIBUTING.md`** — Skills contribution guide (frontmatter, CI, style); entry point for GitHub contributors.
- **`docs/README.md`** — Index of docs by surface (MCP, CLI, SDK) and shared guides.
- **`docs/config.md`** — `PIPEFY_*` environment variables, `config.toml` schema, precedence chain.
- **`docs/parity.md`** — MCP tool ↔ CLI command parity matrix. Source of truth for coverage and deferrals.
- **`docs/MIGRATION.md`** — What existing MCP users need to know about v0.1.
- **`docs/dependencies.md`** — Rationale for runtime dependencies.
- **`docs/architecture.md`**: Intra-package layering (domain, adapter, composition root), type ownership at boundaries, ports, and the alternative-constructor guide.
- **`docs/mcp/tools/`** — Per-area MCP tool reference (parameters, edge cases, cross-cutting behavior). Includes `identifiers.md`, the canonical map of which tool/argument expects slug vs `internal_id` vs uuid vs numeric id.
- **`docs/cli/`** — CLI-specific guides (e.g. introspect-then-execute).
- **`docs/sdk/README.md`** — Using `pipefy` as a library.
- **`skills/AGENTS.md`** — Skill-authoring guide (frontmatter, naming, style). Start here before adding a skill.
- **`skills/onboarding/pipefy-toolkit-setup/`** — First-time setup checklist for agents (links to README snippets; does not own commands).

## Project structure

```
packages/sdk/   → pipefy            (Vendor API SDK — GraphQL, models, services; dist named `pipefy`, import module `pipefy_sdk`)
packages/mcp/   → pipefy-mcp-server (MCP tools, server lifecycle; depends on pipefy)
packages/cli/   → pipefy-cli        (Typer CLI; depends on pipefy)
skills/         → agent skills catalog (Markdown; no Python package)
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

### Parse, don't validate

The boundary check should return a type that carries its result, not a bool or a bare raise that the interior re-derives. Validation that only raises throws away what it learned: the value flows on with its original loose type, so every downstream caller re-checks or re-normalizes it. Parsing turns loose input into a precise type once, and that type carries the proof, so the interior is total.

In practice:

- pydantic-settings models are the parse step for env vars: raw `os.environ` strings in, a typed `PipefySettings` / `AuthSettings` out, illegal values rejected at construction. Normalize there (strip, `rstrip('/')`, lowercase) so no consumer re-normalizes the same field later.
- Prefer a closed sum type over a bag of optionals when inputs are mutually exclusive or co-dependent. `pipefy_auth.resolve_pipefy_auth` returns a `ResolvedAuth` (`StaticTokenAuth | ServiceAccountAuth | StoredSessionAuth`), so the winning credential tier is kept in the type; `build_httpx_auth` is then total over it, with no `None` branch and no fallthrough. Recovering the decision after the fact (an `isinstance` reverse lookup that maps a built `httpx.Auth` back to its tier name) is the anti-pattern this replaces.
- Make illegal states unrepresentable instead of checking for them downstream. A cross-field rule such as "verify_audience requires audience" is a sum type wearing two fields; co-dependent credentials are one optional value, not two independent optionals that a helper later re-assembles.

A function that accepts the parsed type may assume the guarantee and must not re-check it. This pairs with the boundary rule above: that one says where to validate, this one says what the check should hand back.

### Parsed types are self-guaranteeing

A parsed type rejects invalid construction itself; it does not rely on the pipeline that usually builds it. Its constructor enforces every invariant it claims, so holding an instance is proof it is valid and a hand-written instance cannot be invalid. The domain name is the guarantee, not the resolver that happens to produce it.

- A recurring (value + invariant) pair earns a dedicated leaf type rather than a bare `str`, so every field holding one inherits the guarantee instead of re-checking it. A one-off invariant stays with its owner.
- When validity depends on a policy, carry the policy as part of the value so the constructor has the context to judge it.
- A runtime-erased alias does not qualify: it disappears at runtime, so an invalid value still constructs. Reach for a type whose constructor actually runs.
- Settings models stay pure data readers. A cross-field rule fails fast at construction, not through a projection method a consumer must remember to call, which makes the parse optional and invites a silent `None`.

### Composition: the per-app runtime

Parsed types are decisions and cost no I/O to build. Effects (keychain reads, network, building clients or verifiers) live in a per-application runtime built once at startup: the single place raw settings become domain types and wired resources. Downstream depends on the runtime or the types it holds, never on raw settings or an ad-hoc resolve. The runtime lives in the app package; shared packages export parsed types and resolvers, not app wiring or effects. Whether an app wires eagerly (fail fast at boot) or keeps effectful members lazy is a per-app choice.

The layer model this sits inside (domain, adapter, composition root), the rule that domain types do not carry framework or SDK types, and where an alternative constructor lives (classmethod on the type versus free factory in the adapter) are in [`docs/architecture.md`](docs/architecture.md). Intra-package layering is enforced by import-linter in `packages/mcp`; the inter-package direction is enforced by ruff `TID251`.

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
- Sign off every commit (`git commit -s`). CI enforces the Developer Certificate of Origin (DCO), so an unsigned commit fails the check.
- PRs must include: summary, testing performed (commands + results), docs updates if tool behavior or config changed.

## Security
- Credentials via env vars or `.env`; never commit secrets.
- GraphQL schema updates: `uv run gql-cli ...` → update `packages/sdk/tests/services/pipefy/schema.graphql`; see README schema hygiene checklist.
