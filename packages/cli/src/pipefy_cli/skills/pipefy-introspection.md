---
name: pipefy-introspection
description: >
  Use this skill when you need to discover GraphQL type shapes, mutation
  signatures, enum values, or execute arbitrary GraphQL as a fallback.
  This is the first fallback tier (Tier 2) when dedicated MCP tools fail
  or don't exist for an operation. 6 MCP tools.
tags: [pipefy, introspection, graphql, schema, fallback]
---

# Introspection & Raw GraphQL

Schema discovery and a fallback executor. **6 MCP tools.**

This is **Tier 2** in the resolution strategy: when a dedicated MCP tool fails or doesn't exist, use introspection to understand the API, then `execute_graphql` to run the operation directly.

**Tier 1:** dedicated MCP tool exists — use it.
**Tier 2:** use introspection + `execute_graphql` (this skill).
**Tier 3:** direct curl/httpx fallback — see `skills/api-troubleshoot/`.

**CLI status (v0.1):** use the MCP tools in this skill. Dedicated introspect, GraphQL exec, and organization Typer commands are planned for v0.3+.

---

## Tools

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `introspect_type` | — (CLI v0.3+) | Yes | Discover fields, input types, and enums. |
| `introspect_query` | — (CLI v0.3+) | Yes | Get a query's argument types and return shape. |
| `introspect_mutation` | — (CLI v0.3+) | Yes | Get a mutation's argument types and return shape. |
| `search_schema` | — (CLI v0.3+) | Yes | Find types/queries/mutations by keyword. |
| `execute_graphql` | — (CLI v0.3+) | No | Execute arbitrary GraphQL query or mutation. |
| `get_organization` | — (CLI v0.3+) | Yes | Fetch org metadata (plan, members, pipes). |

---

## Steps — discover a mutation signature

1. **Search for the mutation by keyword:**

   MCP: `search_schema keyword="label"`

2. **Get the full mutation signature:**

   MCP: `introspect_mutation mutation_name="createLabel"`

3. **Discover input type fields:**

   MCP: `introspect_type type_name="CreateLabelInput"`

4. **Execute the mutation:**

   MCP:
   ```
   execute_graphql query="mutation CreateLabel($input: CreateLabelInput!) { createLabel(input: $input) { label { id name } } }" variables='{"input": {"pipe_id": 67890, "name": "Urgent", "color": "#FF0000"}}'
   ```

   > **v0.1:** use MCP `execute_graphql` for mutations. A dedicated GraphQL exec CLI wrapper is planned for v0.3+.

---

## Steps — discover a field condition input type

1. `search_schema keyword="fieldCondition"` — find relevant types and mutations.
2. `introspect_mutation mutation_name="createFieldCondition"` — get argument list.
3. `introspect_type type_name="CreateFieldConditionInput"` — discover exact field names and enum values.
4. Use `execute_graphql` or the dedicated tool if one exists.

---

## When to use `execute_graphql`

- A dedicated MCP tool doesn't exist for the operation.
- A tool returns a partial/unexpected response and you need to inspect the raw response.
- You're building a prototype mutation before a tool is implemented.

**Do not use `execute_graphql` as a substitute for dedicated tools** — dedicated tools validate inputs, handle pagination, and format errors consistently.

---

## Success criteria

- `introspect_type` returns the complete field list for the input type.
- `execute_graphql` returns the expected data without errors.

## Failure modes

- **`introspect_type` returns `null`:** type name is case-sensitive — try PascalCase (e.g., `CreateLabelInput`, not `create_label_input`).
- **`execute_graphql` returns GraphQL errors:** check the error `path` and `message`; use `debug=true` on the next call for `correlation_id`.
- **Mutation rejected:** check required fields via `introspect_type`; ensure all non-null fields are provided.

## See also

- `skills/api-troubleshoot/` — Tier 3: direct HTTP fallback when MCP is unavailable.
- `skills/pipes-and-cards/` — most common dedicated tools (prefer over `execute_graphql`).
