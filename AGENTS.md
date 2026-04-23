# Repository Guidelines

## Documentation map
- **`README.md`** — Overview for users and contributors: getting started, MCP tools summary, development, testing, and schema hygiene.
- **`docs/setup.md`** — First-time install, environment variables, MCP client config (optional `bootstrap.sh`).
- **`docs/dependencies.md`** — Rationale for main dependencies.
- **`docs/tools/`** — Per-area reference (parameters, edge cases, cross-cutting behavior). Start from the filenames that match the domain you touch (e.g. `pipes-and-cards.md`, `automations-and-ai.md`, `introspection.md`).

## Project Structure & Module Organization
- `src/pipefy_mcp/` contains the MCP server implementation. Key areas include `tools/` (tool definitions), `services/pipefy/` (GraphQL clients, queries, services), `models/`, and `core/`.
- `tests/` mirrors the source layout with unit tests for tools, services, models, and the server entrypoints.
- `README.md` documents usage, tool behavior, and local development notes (see **Documentation map** above).

## Build, Test and Development Commands
- `uv sync` installs dependencies using `uv` (recommended in this repo).
- `uv run pipefy-mcp-server` runs the MCP server locally via the project script.
- `uv run pytest` runs the full test suite.
- `uv run pytest --cov=src/pipefy_mcp/services/pipefy --cov-report=term-missing` generates a coverage report for Pipefy services.
- `uv run ruff check src/` runs linting.
- `uv run ruff format src/` auto-formats code.

### Manual tool testing (E2E)
- **Preferred:** Use **Cursor’s MCP integration** (add this server in Cursor MCP settings, run `pipefy-mcp-server`, then invoke tools from the chat / MCP panel). This matches how maintainers and agents exercise the server in daily use.
- **After `server.py`, lifespan, or registration changes:** Run a short **Cursor MCP smoke test** (list tools and/or call a read-only tool). See README **Development & Testing → Manual smoke test (Cursor MCP)**.
- **Optional:** `npx @modelcontextprotocol/inspector uv --directory . run pipefy-mcp-server` — MCP Inspector is fine for protocol debugging or when Cursor is not in the loop; it is not the primary sign-off for “tools work for us.”

## Coding Style & Naming Conventions
- Python 3.11+ code lives under `src/` and follows standard module naming (`snake_case` files, `PascalCase` classes).
- Formatting and import sorting are enforced by `ruff` (see `pyproject.toml`). Run format before committing.
- Tests follow `pytest` conventions (`test_*.py`, `Test*`, `test_*`).

## Testing Guidelines
- Framework: `pytest` with `pytest-asyncio`, `pytest-cov`, and `pytest-mock`.
- Keep new tests alongside existing suites in `tests/`, aligned with the module they cover.
- Use markers `@pytest.mark.unit` or `@pytest.mark.integration` when appropriate.
- **Integration (live Pipefy):** Tests marked `@pytest.mark.integration` call the real GraphQL API when `PIPEFY_*` credentials are set in `.env` (skips otherwise).
  - Service layer: `tests/services/pipefy/test_schema_introspection_integration.py`
  - MCP tools (`call_tool` + real `PipefyClient`): `tests/tools/test_introspection_tools_live.py`
  - Full MCP app (`pipefy_mcp.server.mcp` + lifespan + ToolRegistry): `tests/tools/test_pipe_config_tools_live.py` (optional `PIPE_BUILDING_LIVE_PIPE_ID`, `PIPE_BUILDING_LIVE_ORG_ID` — see README); field conditions-only path: `tests/tools/test_field_conditions_tools_live.py` (optional `PIPE_FIELD_CONDITION_LIVE_PHASE_ID`).
  - Run both: `uv run pytest tests/services/pipefy/test_schema_introspection_integration.py tests/tools/test_introspection_tools_live.py -m integration -v`. CI-style run without network: `uv run pytest -m "not integration"`.
  - **Task 6 (release sign-off):** Automated slice `tests/tools/test_task6_mcp_signoff_live.py` + field-condition live test (see README); manual Cursor steps in `.cursor/dev-planning/specs/ai-agents-field-conditions/TASK_6_SIGNOFF.md`.
- **Manual E2E:** After meaningful tool or server changes, smoke-test the affected tools via **Cursor MCP** (see “Manual tool testing” above). Document that in PRs when relevant.
- Examples for targeted runs:
  - Single file: `uv run pytest tests/tools/test_pipe_tools.py`
  - Single test case: `uv run pytest tests/tools/test_pipe_tools.py -k "test_create_card"`

## Adding a New Tool
When implementing a new tool, follow this checklist (TDD-first):

1. **Write tests first** in `tests/tools/` mirroring the source structure (e.g., `test_pipe_tools.py`).
2. **Run the tests and confirm they fail** for the new behavior.
3. **Implement the tool logic** in `src/pipefy_mcp/tools/` (e.g., `pipe_tools.py` or create a new file if appropriate).
4. **Register the tool** by calling the appropriate `*Tools.register(mcp, client)` from `ToolRegistry.register_tools()` in `src/pipefy_mcp/tools/registry.py` (only if not already wired for that domain).
5. **Add the MCP tool name** to **`PIPEFY_TOOL_NAMES`** in `src/pipefy_mcp/tools/registry.py` (same string the client sees). Omitting this breaks startup preflight and `tests/test_server.py`.
6. **Re-run tests and ensure they pass** (including `tests/test_server.py` if the tool list changed).
7. **Update the README** if the tool introduces new user-facing functionality or configuration options.

## Commit & Pull Request Guidelines
- Commit messages follow a conventional style such as `feat:`, `fix:`, `refactor:`, `style:`, `test:`, `docs:` with optional scopes (e.g., `feat(tools): ...`).
- PRs should include a short summary, testing performed (commands and results), and any relevant issue links. Add docs updates if tool behavior or configuration changes.
- **GraphQL-heavy PRs (field conditions, AI Agent read/delete):** Follow the **Schema hygiene checklist** in `README.md` (refresh `tests/services/pipefy/schema.graphql` when needed, run `diff_context.py`, verify `gql()` with live introspection, integration tests). See `.cursor/dev-planning/specs/ai-agents-field-conditions/decisions/ADR-001-schema-hygiene-for-field-conditions-and-ai-agents.md`.

## Security & Configuration Tips
- Local runs require Pipefy service account credentials via env vars (`PIPEFY_OAUTH_CLIENT`, `PIPEFY_OAUTH_SECRET`, etc.). Avoid committing secrets; use local env files or your shell.
- GraphQL schema updates use `uv run gql-cli ...` and should update `tests/services/pipefy/schema.graphql` when needed; see README **Schema hygiene checklist** for field-condition / AI-agent changes.
