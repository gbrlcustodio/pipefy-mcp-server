# Portal

Read Pipefy portals (Interfaces schema): list org portals and fetch full portal detail. **2 tools.**

Portal tools call the **Interfaces** GraphQL endpoint (`PIPEFY_INTERFACES_GRAPHQL_URL`, default `https://app.pipefy.com/graphql/interfaces`), not the public `/graphql` schema used by most pipe/card tools.

---

## Identifiers

| Concept | Tool parameter | Notes |
|--------|----------------|-------|
| **Organization for list** | `organization_uuid` on `list_portals` | Organization **UUID** or **numeric org id** (string or unquoted integer via MCP). Numeric ids are resolved to UUID via public GraphQL before the Interfaces query. |
| **Portal for detail** | `portal_uuid` on `get_portal` | Portal interface UUID from `list_portals` (`uuid` field) or Pipefy UI. |

See [Pipefy IDs in pipes & cards](pipes-and-cards.md#pipefy-ids-type-safety) for MCP integer coercion behavior.

---

## Main vs sub-portals

Each organization has **at most one main portal** (`subType: portal`). Additional entries in `list_portals` may be **sub-portals**. Use `get_portal` for page layout, elements, `published`, and nested `subPortals`.

---

## Tools

| Tool | Read-only | Role |
|------|-----------|------|
| `list_portals` | Yes | Flat list of portals for an org: `uuid`, `name`, `visibility`, `subType`. Does **not** include `published` or page detail — use `get_portal`. Optional `search_term` name filter. |
| `get_portal` | Yes | Full portal: `uuid`, `name`, `visibility`, **`published`**, `pages[]` (with `elements[]`), `subPortals[]`. GraphQL `id` fields are normalized as `uuid` in responses. |

---

## Response shape notes

**`list_portals`** returns `{ portals: [...] }` inside the MCP success envelope. The SDK unwraps Relay `edges` into a flat list.

**`get_portal` page elements** include a `metadata` JSON object whose shape depends on `type` (non-exhaustive):

| Element `type` | Typical `metadata` |
|----------------|-------------------|
| `forms` | `{ formId: str }` |
| `pipe` | `{ pipeId: str }` |
| `link` | `{ url: str, label?: str }` |

Additional element types may appear; treat unknown keys as opaque JSON.

---

## Recommended workflow

1. `list_portals(organization_uuid=...)` — obtain portal UUIDs for the org (numeric org id from URL is fine).
2. `get_portal(portal_uuid=...)` — read pages, elements, publish state, and sub-portals for the portal you need.
