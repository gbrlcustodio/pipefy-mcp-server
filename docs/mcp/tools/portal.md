# Portal

Read and manage Pipefy portals (Interfaces schema): list org portals, fetch detail, create/update/delete portal metadata, manage pages (create, update, delete, sort, layout), manage page elements (create, update, delete, duplicate), and manage sub-portals (create, attach, publish, unpublish, detach, delete). **20 tools** — parity matrix rows in [`docs/parity.md`](../../parity.md).

Most portal tools call the **Interfaces** GraphQL endpoint (`interfaces_graphql_url`, default `https://app.pipefy.com/graphql/interfaces`), derived from `PIPEFY_BASE_URL`. Sub-portal **attach**, **publish**, **unpublish**, **detach**, and **delete** use **internal_api** (`<PIPEFY_BASE_URL>/internal_api`); only **`create_sub_portal`** uses Interfaces (`createSubPortal`).

---

## Endpoints

| Surface | URL (prod default) | Used by |
|---------|-------------------|---------|
| **Interfaces** | `https://app.pipefy.com/graphql/interfaces` | Portal/page/element CRUD, `list_portals`, `get_portal`, `create_sub_portal` |
| **internal_api** | `https://app.pipefy.com/internal_api` | `update_sub_portal_element`, `publish_sub_portal`, `unpublish_sub_portal`, `delete_sub_portal_element`, `delete_sub_portal` |
| **Public GraphQL** | `https://app.pipefy.com/graphql` | Org UUID resolution when `organization_uuid` is numeric (not a portal mutation) |

Set **`PIPEFY_BASE_URL`** once for non-prod hosts; all three paths above follow. Per-URL env vars such as `PIPEFY_INTERFACES_GRAPHQL_URL` are **ignored** (legacy); see [`docs/config.md`](../../config.md#environment-variables).

---

## Permissions

Portal **write** tools require Pipefy permissions on the target organization:

| Permission | Typical use |
|------------|-------------|
| **`create_portal`** | Bootstrap the org main portal (`create_portal`), read paths when the token can manage portals |
| **`manage_portals`** | Page/element CRUD, sub-portal publish/unpublish, destructive deletes |

`PERMISSION_DENIED` on Interfaces or internal_api returns MCP `{ success: false }` with a message naming **`create_portal`** or **`manage_portals`**. Tokens scoped only to pipes/cards (default org on many service accounts) often fail portal writes — use an org where the token has portal admin scope.

Integration tests (`pytest -m integration -k portal`) need **`PIPEFY_PORTAL_ORG_UUID`** pointing at such an org; see [Testing](#testing).

---

## Identifiers

| Concept | Tool parameter | Notes |
|--------|----------------|-------|
| **Organization for list/create** | `organization_uuid` on `list_portals`, `create_portal` | Organization **UUID** or **numeric org id** (string or unquoted integer via MCP). Numeric ids resolve to UUID via public GraphQL before the Interfaces call. |
| **Portal for detail/writes** | `portal_uuid` on `get_portal`, `update_portal`, `delete_portal` | Portal interface UUID from `list_portals` (`uuid`) or Pipefy UI. |
| **GraphQL `id` vs agent `uuid`** | Responses | Interfaces returns field **`id`**; SDK/MCP normalize to **`uuid`** in payloads (same value). |

See [Pipefy IDs in pipes & cards](pipes-and-cards.md#pipefy-ids-type-safety) for MCP integer coercion.

### Wire naming (maintainers)

| Layer | Convention | Examples |
|-------|------------|----------|
| Interfaces mutations | snake_case input fields | `interface_uuid`, `page_id`, `element_id`, `page_ids`, `data_sources`, `repo_uuid` |
| Interfaces exceptions | camelCase | `duplicateElement`: `elementUuid`, `interfaceUuid`, `pageUuid`; `createSubPortal`: `mainPortalUuid` |
| internal_api | camelCase variables | `portalUuid`, `elementId`, `subPortalUuid` |

---

## Main vs sub-portals (publish semantics)

Each organization has **at most one main portal** (`subType: portal`). Additional `list_portals` rows may be **sub-portals**. Use `get_portal` for pages, elements, and nested `subPortals`.

| Surface | `published` meaning |
|---------|---------------------|
| **Main portal** | Always `true` on `get_portal` (Interfaces invariant). **Public** hub access is **`update_portal(visibility="public")`**, not the `published` flag. |
| **Sub-portal** | **`get_portal` → `subPortals[].published`** after attach/publish on a main-portal **`forms`** element. |

Do **not** publish via `createElement(type: subPortal)` — live API expects an existing **`forms`** slot wired with **`updateSubPortalElement`** (internal_api). Sub-portals may also appear under **`pages[].elements[]`** with `type: subPortal` while top-level `subPortals[]` is empty.

**`list_portals`** does not return `published` or page detail — call **`get_portal`**.

---

## Page element types (`InterfacePageElementType`)

Fifteen values accepted by `create_portal_element` / `update_portal_element` (SDK `PortalElementType`):

| `type` | Metadata expectations (SDK) | Agent notes |
|--------|----------------------------|-------------|
| `text` | Opaque JSON | Rich text / static content |
| `table` | Opaque JSON | Table widget |
| `field` | Opaque JSON | Single field display |
| `embedLink` | Opaque JSON | Embedded link |
| `embedVideo` | Opaque JSON | Embedded video |
| `embedImage` | Opaque JSON | Embedded image |
| `button` | Opaque JSON | Action button |
| `divider` | Opaque JSON | Visual separator |
| `link` | **`linkName`** required; optional **`linkUrl`** | Not `url` / `label` |
| `forms` | **`name`** required (non-empty) | Pipe linkage via `data_sources` (`repo_uuid` / `repoId`); **sub-portal publish targets `forms` elements** |
| `pages` | Opaque JSON | Page navigation widget |
| `subPortal` | Optional **`subPortalUuid`** | Prefer internal_api attach/publish; do not rely on `createElement` alone |
| `automationButton` | Opaque JSON | Automation trigger |
| `contentBlock` | Opaque JSON | Content block |
| `document` | Opaque JSON | Document widget |

**`update_portal_element`:** `metadata` is **replace-all** on the wire (`updateElement.metadata` required every time). Send the full blob, not a patch.

**`data_sources`:** Each entry needs a pipe repo id as `repoId`, `repo_uuid`, or `repoUuid` (plus optional `fieldKeys` / `field_keys`). Unknown keys are skipped with an SDK warning.

---

## Tools

| Tool | Read-only | Role |
|------|-----------|------|
| `list_portals` | Yes | Flat list: `uuid`, `name`, `visibility`, `subType`. Optional `search_term`. |
| `get_portal` | Yes | Full portal: `published`, `pages[]`, `elements[]`, `subPortals[]`. |
| `create_portal` | No | Idempotent main portal (`findOrCreateInterfaceByTemplate`). |
| `update_portal` | No | `name`, `visibility` (`internal` \| `private` \| `public`), `color`, `icon`, `display_pipefy_header`. |
| `delete_portal` | No | Irreversible; MCP two-step `confirm`; CLI `--yes`. |
| `create_portal_page` | No | `interface_uuid` + `title`; optional `description`, `index`, `elements`. |
| `update_portal_page` | No | Page metadata; at least one field. |
| `delete_portal_page` | No | Irreversible; destructive hints / `--yes`. |
| `sort_portal_pages` | No | `page_ids` ordered list. |
| `update_portal_page_layout` | No | `page_id` + `layout` JSON only (no portal UUID on wire). |
| `create_portal_element` | No | `page_id`, `type`, `metadata`; optional `data_sources`. |
| `update_portal_element` | No | Full `metadata` replace. |
| `delete_portal_element` | No | Irreversible. |
| `duplicate_portal_element` | No | Same page; `element_id`, `portal_uuid`, `page_id`. |
| `create_sub_portal` | No | Interfaces `createSubPortal`; `main_portal_uuid`, optional `name`. |
| `update_sub_portal_element` | No | Attach (internal_api `updateSubPortalElement`). |
| `publish_sub_portal` | No | Same mutation with `subPortalUuid` on a **`forms`** element. |
| `unpublish_sub_portal` | No | `updateSubPortalElement(subPortalUuid: null)`. |
| `delete_sub_portal_element` | No | Detach wiring (`deleteSubPortalElement`). |
| `delete_sub_portal` | No | Delete interface (`deleteSubPortalInterface`). |

**Layout caveat:** `createElement` does not update the page grid; `duplicateElement` appends layout rows; `deleteElement` does not prune layout unless you pass updated `layout`. Orphan layout references can break the portal viewer (HTTP 500). Prefer disposable pages in smoke tests.

---

## Destructive operations

Portal deletes follow the [cross-cutting two-step contract](cross-cutting.md#destructive-operations): MCP preview (`confirm=false`) then execute (`confirm=true`). CLI uses **`--yes`** (`confirm_destructive`).

Applies to: `delete_portal`, `delete_portal_page`, `delete_portal_element`, `delete_sub_portal`, `delete_sub_portal_element`.

Nested GraphQL/internal_api `success: false` → MCP top-level `{ success: false }`, not a false success envelope.

---

## Sub-portals

### Endpoint map

| MCP tool | GraphQL / API | Endpoint |
|----------|---------------|----------|
| `create_sub_portal` | `createSubPortal` | Interfaces |
| `update_sub_portal_element` | `updateSubPortalElement` | internal_api |
| `publish_sub_portal` | `updateSubPortalElement` (with `subPortalUuid`) | internal_api |
| `unpublish_sub_portal` | `updateSubPortalElement` (`subPortalUuid: null`) | internal_api |
| `delete_sub_portal_element` | `deleteSubPortalElement` | internal_api |
| `delete_sub_portal` | `deleteSubPortalInterface` | internal_api |

### Publish workflow

1. `create_sub_portal(main_portal_uuid, name=…)` → sub-portal UUID.
2. `get_portal(portal_uuid=…)` → pick a **`forms`** element `element_id`.
3. `publish_sub_portal` or `update_sub_portal_element` (both set `subPortalUuid` on the element).
4. `get_portal` → assert **`subPortals[].published`** is `true`.

**Unpublish:** `unpublish_sub_portal` clears the published link; entity remains.

**Detach:** `delete_sub_portal_element` / CLI `sub-portal detach` removes element wiring entirely.

---

## Input validation

| Parameter | Rule |
|-----------|------|
| `portal_uuid` on read/write portal tools | Non-empty string |
| `name`, `color`, `icon` on `update_portal` | Non-empty when provided |
| `update_portal` | At least one updatable field |
| `page_id`, `page_ids[*]` | Non-empty string or positive integer |
| `page_ids` on `sort_portal_pages` | Non-empty list; no duplicates |
| `index` on page create/update | Non-negative integer when set |

---

## Response shape notes

**`list_portals`:** `{ portals: [...] }` inside the MCP envelope (Relay `edges` flattened).

**Permission errors:** `{ success: false }` with `create_portal` / `manage_portals` hints when `PERMISSION_DENIED`.

**`update_portal_element`:** Success echoes submitted `metadata`; use `get_portal` for read-after-write.

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
| `create_sub_portal` | `pipefy portal sub-portal create --main-portal-uuid <uuid> [--name …]` |
| `update_sub_portal_element` | `pipefy portal sub-portal attach <portal-uuid> <element-id> <sub-portal-uuid>` |
| `publish_sub_portal` | `pipefy portal sub-portal publish <portal-uuid> <element-id> <sub-portal-uuid>` |
| `unpublish_sub_portal` | `pipefy portal sub-portal unpublish <portal-uuid> <element-id>` |
| `delete_sub_portal_element` | `pipefy portal sub-portal detach <portal-uuid> <element-id> --yes` |
| `delete_sub_portal` | `pipefy portal sub-portal delete <sub-portal-uuid> --yes` |

---

## Testing

| Mode | Setup |
|------|--------|
| **Unit** | `uv run pytest -m "not integration" -k portal` — fictional IDs in [`fixture_ids.py`](../../../packages/sdk/tests/_shared/fixture_ids.py). |
| **Integration** | `PIPEFY_TOKEN` or service account + **`PIPEFY_PORTAL_ORG_UUID`** in local [`.env`](../../../.env.example) (org where the token has **`manage_portals`**). **`PIPEFY_BASE_URL`** for non-prod. Install: [README#installation](../../../README.md#installation); env reference: [`docs/config.md`](../../config.md#environment-variables). |

---

## Recommended workflow

1. `list_portals(organization_uuid=…)` — portal UUIDs (numeric org id OK).
2. `get_portal(portal_uuid=…)` — pages, elements, publish state.
3. `create_portal(organization_uuid=…)` — bootstrap main portal (idempotent).
4. `update_portal(…, visibility="public")` when the hub should be public.
5. Sub-portals: `create_sub_portal` → **`forms`** element → `publish_sub_portal` → `get_portal` → `unpublish_sub_portal` / delete with confirmation when removing.

---

## Maintainers (TDD and introspection)

When changing portal SDK/MCP/CLI behavior:

1. **Spec:** `.cursor/dev-planning/specs/portal-crud/` (PRD, `introspection-snapshot.md`, `tasks/tasks-portal-crud.md`).
2. **TDD loop:** SDK unit tests → MCP tool tests → CLI tests; `uv run pytest -m "not integration" -k portal`; update [`docs/parity.md`](../../parity.md) in the same PR.
3. **Live schema:** Portal mutations may live on Interfaces or internal_api (see [Endpoints](#endpoints) above), not the main GraphQL URL. Before adding SDK queries, verify shapes with [`skills/introspection/pipefy-introspection/SKILL.md`](../../../skills/introspection/pipefy-introspection/SKILL.md) (`introspect_mutation` / `pipefy introspect mutation`) or `gql-cli` against the derived URLs (set `PIPEFY_BASE_URL` and auth per [`docs/config.md`](../../config.md)):

   ```bash
   uv run gql-cli --headers "Authorization: Bearer $PIPEFY_ACCESS_TOKEN" \
     "$PIPEFY_BASE_URL/graphql/interfaces" \
     -i "query { __type(name: \"Mutation\") { fields { name } } }"
   ```

   ```bash
   uv run gql-cli --headers "Authorization: Bearer $PIPEFY_ACCESS_TOKEN" \
     "$PIPEFY_BASE_URL/internal_api" \
     -i "query { __type(name: \"Mutation\") { fields { name } } }"
   ```

4. **Registry:** add tool names to `PIPEFY_TOOL_NAMES` in `packages/mcp/src/pipefy_mcp/tools/registry.py` and keep the **148** count in `docs/parity.md` in sync.
