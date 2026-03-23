# Introspection & Raw GraphQL

Schema discovery tools plus a last-resort executor. Same OAuth client as everything else. **4 tools.**

Prefer dedicated tools for standard operations. Use these when the schema shifts or no dedicated tool exists.

---

| Tool | Read-only | Role |
|------|-----------|------|
| `introspect_type` | Yes | Type shape: `fields`, `inputFields`, `enumValues`. |
| `introspect_mutation` | Yes | Mutation arguments and return type. |
| `search_schema` | Yes | Keyword search on type names/descriptions. |
| `execute_graphql` | **No** | Arbitrary document (syntax-checked). **Prefer dedicated tools.** |

Responses: `success` / `result` or `error`; transport GraphQL errors are surfaced clearly.
