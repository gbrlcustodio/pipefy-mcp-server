# Portal

Read and manage Pipefy portals (Interfaces schema): list org portals, fetch detail, and create/update/delete portal metadata. **5 tools.**

Portal tools call the **Interfaces** GraphQL endpoint (`PIPEFY_INTERFACES_GRAPHQL_URL`, default `https://app.pipefy.com/graphql/interfaces`), not the public `/graphql` schema used by most pipe/card tools.

---

## Identifiers

| Concept | Tool parameter | Notes |
|--------|----------------|-------|
| **Organization for list/create** | `organization_uuid` on `list_portals`, `create_portal` | Organization **UUID** or **numeric org id** (string or unquoted integer via MCP). Numeric ids are resolved to UUID via public GraphQL before the Interfaces mutation/query. |
| **Portal for detail/writes** | `portal_uuid` on `get_portal`, `update_portal`, `delete_portal` | Portal interface UUID from `list_portals` (`uuid` field) or Pipefy UI. |

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
| `create_portal` | No | Create or fetch the org's main portal (**idempotent**). Uses `findOrCreateInterfaceByTemplate`; a second call returns the same portal UUID. Requires `create_portal` or `manage_portals` permission. |
| `update_portal` | No | Update portal metadata: pass only fields to change (`name`, `visibility`, `color`, `icon`, `display_pipefy_header`). `visibility` must be `internal`, `private`, or `public`. |
| `delete_portal` | No | Delete a portal interface (**irreversible**). `destructiveHint=True`. Two-step MCP flow: call with default `confirm=false` for a preview (`requires_confirmation: true`), then `confirm=true` after explicit approval. CLI uses `--yes` or interactive prompt. |

---

## Destructive delete (`delete_portal`)

MCP agents must use the same two-step pattern as other `delete_*` tools:

1. **Preview:** `delete_portal(portal_uuid="…")` — default `confirm=false`. Returns a preview payload with `requires_confirmation: true`; **does not** call the API.
2. **Execute:** `delete_portal(portal_uuid="…", confirm=true)` — only after human approval.

If GraphQL returns `deleteInterface.success: false`, the tool responds with `{ success: false }` (not a success envelope).

---

## Input validation

| Parameter | Rule |
|-----------|------|
| `portal_uuid` on `get_portal`, `update_portal`, `delete_portal` | Non-empty string (whitespace-only rejected at the MCP boundary). |
| `name`, `color`, `icon` on `update_portal` | When provided, must be non-empty after trimming (whitespace-only rejected). |
| `update_portal` fields | At least one of `name`, `visibility`, `color`, `icon`, `display_pipefy_header` must be set. |

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

**Permission errors** on write tools return `{ success: false }` with a message mentioning `create_portal` or `manage_portals` when the Interfaces API returns `PERMISSION_DENIED`.

---

## CLI parity

| MCP tool | CLI command |
|----------|-------------|
| `list_portals` | `pipefy portal list --organization-uuid <id>` |
| `get_portal` | `pipefy portal get <uuid>` |
| `create_portal` | `pipefy portal create --organization-uuid <id>` |
| `update_portal` | `pipefy portal update <uuid> [--name …] [--visibility …]` |
| `delete_portal` | `pipefy portal delete <uuid> --yes` |

---

## Recommended workflow

1. `list_portals(organization_uuid=...)` — obtain portal UUIDs for the org (numeric org id from URL is fine).
2. `get_portal(portal_uuid=...)` — read pages, elements, publish state, and sub-portals.
3. `create_portal(organization_uuid=...)` — bootstrap the main portal when none exists (safe to call twice).
4. `update_portal(portal_uuid=..., visibility="public")` — change metadata as needed.
5. `delete_portal(portal_uuid=..., confirm=false)` — preview deletion; then `confirm=true` only after explicit approval.
