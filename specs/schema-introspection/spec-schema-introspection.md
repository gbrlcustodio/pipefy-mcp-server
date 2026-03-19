# Schema Introspection & Raw Execution Specification

## Purpose

Provide PipeClaw with a self-healing fallback layer. When dedicated tools don't exist or fail due to API changes, PipeClaw can discover any GraphQL operation via schema introspection and execute it directly. This makes PipeClaw resilient from day one — even before dedicated tools are built for other capabilities.

## Goals

1. PipeClaw can inspect any GraphQL type to understand request/response shapes.
2. PipeClaw can discover mutations and their argument types without prior knowledge.
3. PipeClaw can search the schema by keyword to find relevant operations.
4. PipeClaw can execute arbitrary GraphQL queries and mutations as a last-resort fallback.

## User Stories

- As PipeClaw, when a tool **fails due to API changes**, I want to introspect the schema to discover the correct input shape and retry with a raw GraphQL call.
- As PipeClaw, when **no dedicated tool exists** for a user request, I want to search the schema, inspect the mutation, and execute it directly.
- As PipeClaw, I want to **discover new API capabilities** without waiting for a code release.

## Requirements

### Requirement: Type introspection
The system SHALL allow inspection of any GraphQL type's fields, input fields, or enum values.

#### Scenario: Inspect an object type
- GIVEN a valid GraphQL type name (e.g., `Card`)
- WHEN `introspect_type` is called with that type name
- THEN the tool returns the type's fields with their names, types, and descriptions

#### Scenario: Inspect an input type
- GIVEN a valid GraphQL input type name (e.g., `CreateCardInput`)
- WHEN `introspect_type` is called with that type name
- THEN the tool returns the input fields with their names, types, whether they are required, and descriptions

#### Scenario: Inspect an enum type
- GIVEN a valid GraphQL enum type name
- WHEN `introspect_type` is called with that type name
- THEN the tool returns the enum values with their names and descriptions

#### Scenario: Type not found
- GIVEN an invalid or nonexistent type name
- WHEN `introspect_type` is called
- THEN the tool returns a clear error message indicating the type was not found

### Requirement: Mutation introspection
The system SHALL allow inspection of any GraphQL mutation's name, description, and argument types.

#### Scenario: Inspect a mutation
- GIVEN a valid mutation name (e.g., `createCard`)
- WHEN `introspect_mutation` is called with that mutation name
- THEN the tool returns the mutation's name, description, arguments (name, type, required), and return type

#### Scenario: Mutation not found
- GIVEN an invalid or nonexistent mutation name
- WHEN `introspect_mutation` is called
- THEN the tool returns a clear error message indicating the mutation was not found

### Requirement: Schema search
The system SHALL allow keyword search across the GraphQL schema, returning matching type names, kinds, and descriptions.

#### Scenario: Search with matching results
- GIVEN a keyword (e.g., `pipe`)
- WHEN `search_schema` is called with that keyword
- THEN the tool returns all types whose name or description matches (case-insensitive), including their kind (OBJECT, INPUT_OBJECT, ENUM, etc.)

#### Scenario: Search with no matches
- GIVEN a keyword that matches nothing in the schema
- WHEN `search_schema` is called
- THEN the tool returns an empty list of matching types (e.g. `types: []` in the payload), without requiring a dedicated human-readable message

### Requirement: Raw GraphQL execution
The system SHALL allow execution of arbitrary GraphQL queries and mutations with variables, returning the raw JSON response.

#### Scenario: Execute a valid query
- GIVEN a valid GraphQL query string and variables
- WHEN `execute_graphql` is called
- THEN the tool executes the query against the standard GraphQL endpoint and returns the data

#### Scenario: Execute a valid mutation
- GIVEN a valid GraphQL mutation string and variables
- WHEN `execute_graphql` is called
- THEN the tool executes the mutation and returns the result data

#### Scenario: GraphQL errors in response
- GIVEN a query that produces GraphQL-level errors (e.g., invalid field, permission denied)
- WHEN `execute_graphql` is called
- THEN the tool returns the errors clearly surfaced in the response, not swallowed

#### Scenario: Syntax error in query
- GIVEN a malformed GraphQL string
- WHEN `execute_graphql` is called
- THEN the tool validates syntax via `gql()` before sending and returns a clear validation error

### Requirement: Read-only hints
The system SHALL mark introspection tools as read-only and the execution tool as read-write.

#### Scenario: Tool annotations
- GIVEN the four tools in this capability
- WHEN they are registered with the MCP server
- THEN `introspect_type`, `introspect_mutation`, and `search_schema` have `readOnlyHint=True`
- AND `execute_graphql` has `readOnlyHint=False`

### Requirement: Standard endpoint only
The system SHALL execute raw GraphQL against the standard Pipefy GraphQL endpoint only, not the internal API endpoint.

#### Scenario: Endpoint targeting
- GIVEN a raw GraphQL call via `execute_graphql`
- WHEN the query is executed
- THEN it targets the standard GraphQL endpoint (`PIPEFY_GRAPHQL_URL`)
- AND the internal API endpoint is never used by this tool

## Non-Goals

- **No guardrails or blocklist** on `execute_graphql`. The MCP is a toolbox — security responsibility belongs to the agent's operational rules (AGENTS.md). The service account already scopes access to the org.
- **No internal API support.** The `internal_api` endpoint is fully covered by dedicated AI Automation tools. A separate `execute_internal_graphql` can be added later if needed.
- **No query caching.** Schema introspection results are not cached across calls (each call is fresh).

## Technical Context

### Architecture

Follows existing patterns:

| Layer | File | Responsibility |
|-------|------|---------------|
| Queries | `services/pipefy/queries/introspection_queries.py` | `gql()` constants for `__type` and `__schema` introspection queries |
| Service | `services/pipefy/schema_introspection_service.py` | Methods: `introspect_type()`, `introspect_mutation()`, `search_schema()`, `execute_graphql()` |
| Facade | `services/pipefy/client.py` | Delegate to `SchemaIntrospectionService` |
| Tools | `tools/introspection_tools.py` | Register 4 tools via `@mcp.tool()`, delegate to `PipefyClient` |
| Helpers | `tools/introspection_tool_helpers.py` | `build_success_payload` / `build_error_payload` (JSON text for MCP); legacy names (`build_introspection_*`, `build_execute_*`) may alias the same implementations |

### Service design

- `SchemaIntrospectionService` extends `BasePipefyClient` (receives `PipefySettings` + shared `auth`).
- `execute_graphql` accepts a raw query string, wraps it with `gql(query_string)` internally to validate syntax, then calls `execute_query`.
- Returns raw `dict` responses (no TypedDict — response shape is dynamic by nature).
- Error handling: catch `TransportQueryError` and `GraphQLError` from the `gql`/GraphQL stack and surface errors clearly in the response (do not swallow them).

### Wiring

- `PipefyClient.__init__` creates `SchemaIntrospectionService` alongside existing services.
- `ToolRegistry.register_tools()` calls `IntrospectionTools.register(mcp, client)`.
- `ServicesContainer` — no changes needed (service lives inside `PipefyClient`).

### Delivery note

Initial planning suggested a small PR (≤10 files, ≤300 lines). The shipped capability merged to `main` with a fuller test matrix: unit tests, MCP scenario tests, optional live Pipefy integration (`@pytest.mark.integration`), and MCP `call_tool` smoke tests against a real client when credentials exist.

### Verification and CI

- Tests marked `@pytest.mark.integration` may call the live Pipefy GraphQL API when `PIPEFY_*` credentials are configured (they skip otherwise).
- Default CI runs `pytest -m "not integration"` so pipelines do not depend on secrets or external availability.

## Open Questions

None — all design decisions were resolved in the PRD (see `specs/pipeclaw-full-toolset/prd-pipeclaw-full-toolset.md`, Decisions Log #6 and #7).
