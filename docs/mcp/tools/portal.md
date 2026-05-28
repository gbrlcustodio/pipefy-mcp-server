# Portal

Read and manage Pipefy portals (Interfaces schema): list org portals, fetch detail, create/update/delete portal metadata, manage pages (create, update, delete, sort, layout), and manage page elements (create, update, delete, duplicate). **14 tools.**

Portal tools call the **Interfaces** GraphQL endpoint (`<PIPEFY_BASE_URL>/graphql/interfaces`, default `https://app.pipefy.com/graphql/interfaces`), not the public `/graphql` schema used by most pipe/card tools.

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
| `create_portal_page` | No | Create a page on a portal (`interface_uuid` + `title`). Omitting `elements` on the API may bootstrap a templated page with default widgets. |
| `update_portal_page` | No | Update page metadata (`title`, `description`, `index`); pass only fields to change. |
| `delete_portal_page` | No | Delete a page (**irreversible**). `destructiveHint=True`; CLI requires `--yes`. |
| `sort_portal_pages` | No | Reorder pages via `page_ids` list. |
| `update_portal_page_layout` | No | Replace the page grid layout JSON (`page_id` + `layout` only — no portal UUID). |
| `create_portal_element` | No | Add a widget to a page (`page_id`, `type`, `metadata`; optional `data_sources`). Validates metadata before GraphQL. |
| `update_portal_element` | No | Replace element metadata in full (`element_id`, `page_id`, `type`, complete `metadata`). |
| `delete_portal_element` | No | Delete a page element (**irreversible**). `destructiveHint=True`; CLI `--yes`. |
| `duplicate_portal_element` | No | Duplicate an element on the **same** page (`element_id`, `portal_uuid`, `page_id` = source portal/page). |

**Layout caveat (Pipefy UI):** `createElement` does not update the page grid; `duplicateElement` appends layout rows; `deleteElement` does not prune layout unless you pass an updated `layout`. Orphan layout references can crash the portal viewer (HTTP 500). Prefer smoke on disposable pages and delete them after tests.

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
| `page_id`, `page_ids[*]` on page tools | Non-empty string or positive integer (same `validate_tool_id` rules as `portal_uuid` on other portal tools — not a strict UUID regex). |
| `page_ids` on `sort_portal_pages` | Non-empty list; no duplicate entries after cleaning. |
| `index` on `create_portal_page`, `update_portal_page` | When provided, non-negative integer (`>= 0`). |

---

## Response shape notes

**`list_portals`** returns `{ portals: [...] }` inside the MCP success envelope. The SDK unwraps Relay `edges` into a flat list.

**`get_portal` page elements** include a `metadata` JSON object whose shape depends on `type` (non-exhaustive):

| Element `type` | Typical `metadata` |
|----------------|-------------------|
| `forms` | `{ name: str, defaultValues?: object, emailCollector?: bool, connectedFieldsFilters?: array, ... }` |
| `pipe` | `{ pipeId: str }` |
| `link` | `{ linkName: str, linkUrl?: str, gridMap?: object }` |

Additional element types may appear; treat unknown keys as opaque JSON.

**Permission errors** on write tools return `{ success: false }` with a message mentioning `create_portal` or `manage_portals` when the Interfaces API returns `PERMISSION_DENIED`.

**`update_portal_element` metadata:** The tool success payload echoes the validated `metadata` you sent. Interfaces `updateElement` returns only `success`, not the stored element. Use `get_portal` for read-after-write state.

**`data_sources` on create/update element:** Each entry must include a pipe repo id as `repoId`, `repo_uuid`, or `repoUuid` (plus optional `fieldKeys` / `field_keys`). Unrecognized keys (e.g. `pipe_id`) are skipped; the SDK logs a warning and sends no binding for that entry.

---

## CLI parity

| MCP tool | CLI command |
|----------|-------------|
| `list_portals` | `pipefy portal list --organization-uuid <id>` |
| `get_portal` | `pipefy portal get <uuid>` |
| `create_portal` | `pipefy portal create --organization-uuid <id>` |
| `update_portal` | `pipefy portal update <uuid> [--name …] [--visibility …]` |
| `delete_portal` | `pipefy portal delete <uuid> --yes` |
| `create_portal_page` | `pipefy portal page create --portal-uuid <uuid> --title <title>` |
| `update_portal_page` | `pipefy portal page update <portal-uuid> <page-uuid> [--title …]` |
| `delete_portal_page` | `pipefy portal page delete <portal-uuid> <page-uuid> --yes` |
| `sort_portal_pages` | `pipefy portal page sort --portal-uuid <uuid> --page-ids id1,id2` |
| `update_portal_page_layout` | `pipefy portal page layout update --page-id <uuid> --layout '{…}'` |
| `create_portal_element` | `pipefy portal element create --page-id <uuid> --type forms --metadata '{…}'` |
| `update_portal_element` | `pipefy portal element update <element-uuid> <page-uuid> --type link --metadata '{…}'` |
| `delete_portal_element` | `pipefy portal element delete <element-uuid> <page-uuid> --yes` |
| `duplicate_portal_element` | `pipefy portal element duplicate --element-id <uuid> --portal-uuid <uuid> --page-id <uuid>` |

---

## Testing

| Mode | Org / pipe identifiers |
|------|-------------------------|
| **Unit** (`pytest -m "not integration"`) | Fictional fixtures only — [`fixture_ids.py`](../../../packages/sdk/tests/_shared/fixture_ids.py). Never hardcode production org UUIDs in test code. |
| **Integration** (`pytest -m integration`) | Set `PIPEFY_PORTAL_ORG_UUID` in local [`.env`](../../../.env.example) (org where the token has `manage_portals`). See [setup.md](../../setup.md#quick-start). |

---

## Recommended workflow

1. `list_portals(organization_uuid=...)` — obtain portal UUIDs for the org (numeric org id from URL is fine).
2. `get_portal(portal_uuid=...)` — read pages, elements, publish state, and sub-portals.
3. `create_portal(organization_uuid=...)` — bootstrap the main portal when none exists (safe to call twice).
4. `update_portal(portal_uuid=..., visibility="public")` — change metadata as needed.
5. `delete_portal(portal_uuid=..., confirm=false)` — preview deletion; then `confirm=true` only after explicit approval.
