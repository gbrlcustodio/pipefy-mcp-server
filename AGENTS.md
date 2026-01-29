# Repository Guidelines

## Project Structure & Module Organization
- `src/pipefy_mcp/` contains the MCP server implementation. Key areas include `tools/` (tool definitions), `services/pipefy/` (GraphQL clients, queries, services), `models/`, and `core/`.
- `tests/` mirrors the source layout with unit tests for tools, services, models, and the server entrypoints.
- `README.md` documents usage, tool behavior, and local development notes.

## Build, Test, and Development Commands
- `uv sync` installs dependencies using `uv` (recommended in this repo).
- `uv run pipefy-mcp-server` runs the MCP server locally via the project script.
- `uv run pytest` runs the full test suite.
- `uv run pytest --cov=src/pipefy_mcp/services/pipefy --cov-report=term-missing` generates a coverage report for Pipefy services.
- `uv run ruff check src/` runs linting.
- `uv run ruff format src/` auto-formats code.
- `npx @modelcontextprotocol/inspector uv --directory . run pipefy-mcp-server` launches the MCP Inspector for manual tool testing.

## Coding Style & Naming Conventions
- Python 3.11+ code lives under `src/` and follows standard module naming (`snake_case` files, `PascalCase` classes).
- Formatting and import sorting are enforced by `ruff` (see `pyproject.toml`). Run format before committing.
- Tests follow `pytest` conventions (`test_*.py`, `Test*`, `test_*`).

## Testing Guidelines
- Framework: `pytest` with `pytest-asyncio`, `pytest-cov`, and `pytest-mock`.
- Keep new tests alongside existing suites in `tests/`, aligned with the module they cover.
- Use markers `@pytest.mark.unit` or `@pytest.mark.integration` when appropriate.
- Examples for targeted runs:
  - Single file: `uv run pytest tests/tools/test_cards.py`
  - Single test case: `uv run pytest tests/tools/test_cards.py -k "test_create_card"`

## Commit & Pull Request Guidelines
- Commit messages follow a conventional style such as `feat:`, `fix:`, `refactor:`, `style:`, `test:`, `docs:` with optional scopes (e.g., `feat(tools): ...`).
- PRs should include a short summary, testing performed (commands and results), and any relevant issue links. Add docs updates if tool behavior or configuration changes.

## Security & Configuration Tips
- Local runs require Pipefy service account credentials via env vars (`PIPEFY_OAUTH_CLIENT`, `PIPEFY_OAUTH_SECRET`, etc.). Avoid committing secrets; use local env files or your shell.
- GraphQL schema updates use `uv run gql-cli ...` and should update `tests/services/pipefy/schema.graphql` when needed.
