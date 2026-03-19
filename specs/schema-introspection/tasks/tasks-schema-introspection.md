# Schema Introspection Tasks

> **Goal**: 4 MCP tools for GraphQL introspection and raw execution — PipeClaw's self-healing fallback
> **Spec**: [../spec-schema-introspection.md](../spec-schema-introspection.md)
> **Prerequisite**: None (Phase 0 — foundational, no dependencies)

---

## Relevant Files

- `src/pipefy_mcp/services/pipefy/queries/introspection_queries.py` - `gql()` constants for `__type`, `__schema`, and mutation introspection
- `src/pipefy_mcp/services/pipefy/schema_introspection_service.py` - Service with introspect/search/execute methods
- `src/pipefy_mcp/services/pipefy/client.py` - Facade delegation to SchemaIntrospectionService
- `src/pipefy_mcp/tools/introspection_tools.py` - MCP tool registration for 4 tools
- `src/pipefy_mcp/tools/introspection_tool_helpers.py` - Payload builders for introspection responses
- `src/pipefy_mcp/tools/registry.py` - ToolRegistry wiring
- `tests/services/pipefy/test_schema_introspection_service.py` - Service unit tests
- `tests/tools/test_introspection_tools.py` - Tool unit tests
- `README.md` - Documentation for new tools

### Notes

- Unit tests mirror `src/` structure under `tests/`.
- Run `uv run pytest tests/services/pipefy/test_schema_introspection_service.py -v` for service tests.
- Run `uv run pytest tests/tools/test_introspection_tools.py -v` for tool tests.

---

## Trigger / Enables / Depends on

**Trigger:** PipeClaw encounters an API operation with no dedicated tool, or a dedicated tool fails due to API changes.
**Enables:** All future phases (1-6) — PipeClaw can operate via raw GraphQL even before dedicated tools are built. Also enables field type discovery for Phase 1 (Pipe Building).
**Depends on:** Nothing — this is Phase 0.

---

## Acceptance Criteria

- [x] `introspect_type` returns fields/inputFields/enumValues for any valid GraphQL type
- [x] `introspect_mutation` returns name, description, args, and return type for any mutation
- [x] `search_schema` returns matching types by keyword (case-insensitive)
- [x] `execute_graphql` executes arbitrary queries/mutations and returns raw JSON
- [x] `execute_graphql` validates syntax via `gql()` before sending
- [x] `execute_graphql` surfaces GraphQL errors clearly (not swallowed)
- [x] Introspection tools have `readOnlyHint=True`; `execute_graphql` has `readOnlyHint=False`
- [x] All tools target the standard GraphQL endpoint only

---

## Task 1: Define introspection GraphQL queries

- [x] **1.1** Create introspection_queries.py with type introspection query
  - **File**: `src/pipefy_mcp/services/pipefy/queries/introspection_queries.py` (create new)
  - **What**: Define `INTROSPECT_TYPE_QUERY` as a `gql()` constant using GraphQL's `__type(name: $typeName)` introspection. Return `name`, `kind`, `description`, `fields { name type { name kind ofType { name kind } } description }`, `inputFields` (same shape), and `enumValues { name description }`.
  - **Why**: Foundation for `introspect_type` — lets PipeClaw discover any type's structure.
  - **Pattern**: Follow `src/pipefy_mcp/services/pipefy/queries/pipe_queries.py` — `gql()` constants with variables.
  - **Verify**: File exists, imports `gql`, defines the constant.

- [x] **1.2** Add mutation introspection query
  - **File**: `src/pipefy_mcp/services/pipefy/queries/introspection_queries.py` (modify)
  - **What**: Define `INTROSPECT_MUTATION_QUERY` using `__type(name: "Mutation")` to get a specific field by name. Query: `__type(name: "Mutation") { fields { name description args { name type { name kind ofType { name kind } } defaultValue } type { name kind } } }`. The service will filter by mutation name.
  - **Why**: Lets PipeClaw discover any mutation's argument types before executing it.
  - **Pattern**: Same file, same `gql()` pattern.
  - **Verify**: Constant defined and parseable.

- [x] **1.3** Add schema types listing query
  - **File**: `src/pipefy_mcp/services/pipefy/queries/introspection_queries.py` (modify)
  - **What**: Define `SCHEMA_TYPES_QUERY` using `__schema { types { name kind description } }` to list all types. The service will filter by keyword.
  - **Why**: Foundation for `search_schema` — PipeClaw can discover relevant operations by keyword.
  - **Pattern**: Same file, same `gql()` pattern.
  - **Verify**: Constant defined and parseable.

---

## Task 2: Create SchemaIntrospectionService (TDD)

**Depends on:** Task 1 (queries must exist).

- [x] **2.1** Write tests for introspect_type
  - **File**: `tests/services/pipefy/test_schema_introspection_service.py` (create new)
  - **What**: Test cases: (a) inspect object type returns fields, (b) inspect input type returns inputFields, (c) inspect enum returns enumValues, (d) type not found returns clear error.
  - **Why**: TDD — tests first, red phase.
  - **Pattern**: Follow `tests/services/pipefy/test_card_service.py` — mock `execute_query`, assert return shape.
  - **Verify**: `uv run pytest tests/services/pipefy/test_schema_introspection_service.py -k "introspect_type" -v` — tests fail (red).

- [x] **2.2** Implement introspect_type method
  - **File**: `src/pipefy_mcp/services/pipefy/schema_introspection_service.py` (create new)
  - **What**: Create `SchemaIntrospectionService(BasePipefyClient)`. Method `async introspect_type(type_name: str) -> dict` calls `execute_query(INTROSPECT_TYPE_QUERY, {"typeName": type_name})`. If `__type` is `None`, return error dict. Otherwise return the type data.
  - **Why**: Core introspection method — PipeClaw's primary way to understand API shapes.
  - **Pattern**: Follow `src/pipefy_mcp/services/pipefy/card_service.py` — extends `BasePipefyClient`, uses `execute_query`.
  - **Verify**: `uv run pytest tests/services/pipefy/test_schema_introspection_service.py -k "introspect_type" -v` — tests pass (green).

- [x] **2.3** Write tests for introspect_mutation
  - **File**: `tests/services/pipefy/test_schema_introspection_service.py` (modify)
  - **What**: Test cases: (a) inspect valid mutation returns name, args, return type, (b) mutation not found returns clear error.
  - **Why**: TDD red phase.
  - **Pattern**: Same test file, same mock pattern.
  - **Verify**: Tests fail (red).

- [x] **2.4** Implement introspect_mutation method
  - **File**: `src/pipefy_mcp/services/pipefy/schema_introspection_service.py` (modify)
  - **What**: Method `async introspect_mutation(mutation_name: str) -> dict`. Calls `execute_query(INTROSPECT_MUTATION_QUERY)`, filters `fields` list by `name == mutation_name`. If not found, return error dict. Otherwise return the mutation's description, args, and return type.
  - **Why**: PipeClaw can discover any mutation's signature before building a raw query.
  - **Pattern**: Same service, same `execute_query` pattern.
  - **Verify**: Tests pass (green).

- [x] **2.5** Write tests for search_schema
  - **File**: `tests/services/pipefy/test_schema_introspection_service.py` (modify)
  - **What**: Test cases: (a) search with matching results returns types with name/kind/description, (b) no matches returns empty list, (c) search is case-insensitive, (d) internal types (starting with `__`) are excluded.
  - **Why**: TDD red phase.
  - **Verify**: Tests fail (red).

- [x] **2.6** Implement search_schema method
  - **File**: `src/pipefy_mcp/services/pipefy/schema_introspection_service.py` (modify)
  - **What**: Method `async search_schema(keyword: str) -> dict`. Calls `execute_query(SCHEMA_TYPES_QUERY)`, filters types where `keyword.lower()` appears in `name.lower()` or `(description or "").lower()`. Excludes types starting with `__`. Returns list of matching types.
  - **Why**: PipeClaw can discover relevant API operations by keyword.
  - **Pattern**: Same service; filtering is done in Python, not GraphQL.
  - **Verify**: Tests pass (green).

- [x] **2.7** Write tests for execute_graphql
  - **File**: `tests/services/pipefy/test_schema_introspection_service.py` (modify)
  - **What**: Test cases: (a) valid query returns data, (b) valid mutation returns data, (c) GraphQL errors are surfaced clearly, (d) syntax error in query string raises/returns validation error.
  - **Why**: TDD red phase.
  - **Verify**: Tests fail (red).

- [x] **2.8** Implement execute_graphql method
  - **File**: `src/pipefy_mcp/services/pipefy/schema_introspection_service.py` (modify)
  - **What**: Method `async execute_graphql(query: str, variables: dict | None = None) -> dict`. Wraps `query` with `gql(query)` to validate syntax (catch `GraphQLSyntaxError` and return clear error). Then calls `execute_query(parsed_query, variables or {})`. Catches `TransportQueryError` and surfaces GraphQL errors.
  - **Why**: The ultimate fallback — PipeClaw can execute any GraphQL operation.
  - **Pattern**: Uses `gql()` from the `gql` package for syntax validation; same `execute_query` for execution.
  - **Verify**: Tests pass (green).

---

## Task 3: Wire service into PipefyClient facade

**Depends on:** Task 2 (service must exist).

- [x] **3.1** Add SchemaIntrospectionService to PipefyClient
  - **File**: `src/pipefy_mcp/services/pipefy/client.py` (modify)
  - **What**: Import `SchemaIntrospectionService`. In `__init__`, create `self._introspection_service = SchemaIntrospectionService(settings=settings, auth=auth)`. Add 4 delegate methods: `introspect_type`, `introspect_mutation`, `search_schema`, `execute_graphql`.
  - **Why**: Maintains the facade pattern — tools call `PipefyClient`, not services directly.
  - **Pattern**: Follow existing `_pipe_service` / `_card_service` pattern in `client.py`.
  - **Integration**: Tools in Task 4 will call these facade methods.
  - **Verify**: `from pipefy_mcp.services.pipefy.client import PipefyClient` works; methods exist.

- [x] **3.2** Export service from package
  - **File**: `src/pipefy_mcp/services/pipefy/__init__.py` (modify)
  - **What**: Add `SchemaIntrospectionService` to `__all__` and imports.
  - **Why**: Clean public API.
  - **Pattern**: Follow existing exports in the file.
  - **Verify**: `from pipefy_mcp.services.pipefy import SchemaIntrospectionService` works.

---

## Task 4: Create introspection MCP tools + helpers (TDD)

**Depends on:** Task 3 (facade must exist).

- [x] **4.1** Create introspection_tool_helpers.py
  - **File**: `src/pipefy_mcp/tools/introspection_tool_helpers.py` (create new)
  - **What**: Define payload builders: `build_introspection_success_payload(data)`, `build_introspection_error_payload(error_message)`, `build_execute_success_payload(data)`, `build_execute_error_payload(error_message)`. Format introspection results as readable text for LLM consumption.
  - **Why**: Keeps tool files focused on MCP registration; shared formatting logic lives here.
  - **Pattern**: Follow `src/pipefy_mcp/tools/pipe_tool_helpers.py`.
  - **Verify**: File imports cleanly.

- [x] **4.2** Write tests for introspection tools
  - **File**: `tests/tools/test_introspection_tools.py` (create new)
  - **What**: Test all 4 tools end-to-end (mocking `PipefyClient`): (a) `introspect_type` success and not-found, (b) `introspect_mutation` success and not-found, (c) `search_schema` with results and empty, (d) `execute_graphql` success, GraphQL error, and syntax error.
  - **Why**: TDD red phase for tool layer.
  - **Pattern**: Follow `tests/tools/test_pipe_tools.py` — mock client, call tool function, assert response.
  - **Verify**: Tests fail (red).

- [x] **4.3** Implement introspect_type tool
  - **File**: `src/pipefy_mcp/tools/introspection_tools.py` (create new)
  - **What**: Create `IntrospectionTools` class with `@staticmethod register(mcp, client)`. Define `introspect_type` tool with `@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))`. Params: `type_name: str`. Docstring: action description for LLM routing. Delegate to `client.introspect_type(type_name)`.
  - **Why**: First of the 4 introspection tools — inspect any GraphQL type's shape.
  - **Pattern**: Follow `src/pipefy_mcp/tools/pipe_tools.py` — closure-based registration.
  - **Verify**: Tests for this tool pass (green).

- [x] **4.4** Implement introspect_mutation tool
  - **File**: `src/pipefy_mcp/tools/introspection_tools.py` (modify)
  - **What**: Add `introspect_mutation` tool with `readOnlyHint=True`. Params: `mutation_name: str`. Delegate to `client.introspect_mutation(mutation_name)`.
  - **Why**: PipeClaw can discover any mutation's arguments before executing it.
  - **Verify**: Tests pass.

- [x] **4.5** Implement search_schema tool
  - **File**: `src/pipefy_mcp/tools/introspection_tools.py` (modify)
  - **What**: Add `search_schema` tool with `readOnlyHint=True`. Params: `keyword: str`. Delegate to `client.search_schema(keyword)`.
  - **Why**: PipeClaw can find relevant API operations by keyword.
  - **Verify**: Tests pass.

- [x] **4.6** Implement execute_graphql tool
  - **File**: `src/pipefy_mcp/tools/introspection_tools.py` (modify)
  - **What**: Add `execute_graphql` tool with `readOnlyHint=False`. Params: `query: str`, `variables: dict | None = None`. Docstring: *"Prefer dedicated tools when available. Use this as a fallback when no specific tool exists. Always introspect the mutation's input shape before executing."* Delegate to `client.execute_graphql(query, variables)`.
  - **Why**: The ultimate fallback — execute any GraphQL operation directly.
  - **Verify**: All tool tests pass (green).

---

## Task 5: Register tools and update README

**Depends on:** Task 4 (tools must exist).

- [x] **5.1** Register IntrospectionTools in ToolRegistry
  - **File**: `src/pipefy_mcp/tools/registry.py` (modify)
  - **What**: Import `IntrospectionTools`. Add `IntrospectionTools.register(self.mcp, self.services_container.pipefy_client)` in `register_tools()`.
  - **Why**: Makes the 4 tools available to LLM clients.
  - **Pattern**: Follow existing `PipeTools.register(...)` call.
  - **Verify**: `uv run pytest` — all tests pass. `uv run ruff check src/ && uv run ruff format src/` — no lint errors.

- [x] **5.2** Update README with introspection tools
  - **File**: `README.md` (modify)
  - **What**: Add "Introspection Tools" section documenting `introspect_type`, `introspect_mutation`, `search_schema`, `execute_graphql` with brief descriptions and usage notes.
  - **Why**: User-facing documentation for the new capability.
  - **Pattern**: Follow existing tool documentation format in README.
  - **Verify**: README renders correctly.

---

## Definition of Done

- [x] All 4 tools callable via MCP Inspector: `introspect_type`, `introspect_mutation`, `search_schema`, `execute_graphql` — verified via `tests/test_server.py::test_register_tools` (`list_tools`); manual check: `npx @modelcontextprotocol/inspector uv --directory . run pipeclaw`
- [x] `uv run pytest` — full test suite passes
- [x] `uv run pytest --cov=src/pipefy_mcp/services/pipefy --cov-report=term-missing` — ≥95% coverage on new service (`schema_introspection_service.py` at 98%)
- [x] `uv run ruff check src/ && uv run ruff format src/` — no lint errors
- [x] README documents all 4 new tools
