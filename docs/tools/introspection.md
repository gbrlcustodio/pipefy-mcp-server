# Introspection & Raw GraphQL

Schema discovery tools plus a last-resort executor. Same OAuth client as everything else. **6 tools.**

Prefer dedicated tools for standard operations. Use these when the schema shifts or no dedicated tool exists.

---

| Tool | Read-only | Role |
|------|-----------|------|
| `introspect_type` | Yes | Type shape: `fields`, `inputFields`, `enumValues`. Optional `max_depth` for sub-type resolution. |
| `introspect_query` | Yes | Query arguments and return type. Optional `max_depth`. |
| `introspect_mutation` | Yes | Mutation arguments and return type. Optional `max_depth`. |
| `search_schema` | Yes | Keyword search on type names/descriptions. Optional `kind` filter. |
| `execute_graphql` | **No** | Arbitrary document (syntax-checked). Hints query/mutation mismatch on errors. **Prefer dedicated tools.** |

Responses: `success` / `result` or `error`; transport GraphQL errors are surfaced clearly.

## `max_depth` parameter

`introspect_type`, `introspect_query`, and `introspect_mutation` accept an optional `max_depth` (default `1`).

- **`max_depth=1`** (default) — returns the type/field info as-is. No sub-type resolution.
- **`max_depth=2`** — resolves one level of referenced types. Each non-scalar field/arg gets a `resolvedType` key with the full type definition inlined.

This eliminates the common multi-call pattern where the agent first introspects a mutation, then separately introspects each input type. With `max_depth=2`, a single call like `introspect_mutation("createCard", max_depth=2)` returns `CreateCardInput` with all its `inputFields` inlined.

Scalar types (`ID`, `String`, `Int`, `Float`, `Boolean`, `DateTime`) are never resolved.

## `kind` filter on `search_schema`

`search_schema` accepts an optional `kind` parameter to filter results by GraphQL type kind:

- `OBJECT` — output types (Card, Pipe, User, ...)
- `INPUT_OBJECT` — mutation inputs (CreateCardInput, ...)
- `ENUM` — enumeration types (CardStatus, ...)
- `SCALAR`, `INTERFACE`, `UNION` — other type kinds

Example: `search_schema("automation", kind="INPUT_OBJECT")` returns only automation-related input types.

## Query/mutation mismatch hint

When `execute_graphql` fails with a "field not found" error, the service checks if the field exists on the other root type (Query vs Mutation). If found, the error includes a `hint` key:

```json
{
  "message": "Cannot query field 'createCard' on type 'Query'.",
  "hint": "Hint: 'createCard' exists as a mutation, not a query. Use a mutation operation instead."
}
```

This catches the common mistake of using `query { createCard(...) }` instead of `mutation { createCard(...) }`.
