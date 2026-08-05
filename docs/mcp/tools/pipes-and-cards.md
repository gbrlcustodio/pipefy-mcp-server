# Pipes & Cards

Read, create, update, and delete pipes, phases, phase fields, labels, cards, and field conditions. **41 tools.** (Card-to-card relation tools `get_card_relations` / `delete_card_relation` / `create_card_relation` are documented in [Connections & Relations](relations.md).)

## Cross-cutting patterns

- **Field types** are not validated locally — use `introspect_type` (e.g. on `CreatePhaseFieldInput`) for allowed values.
- Successful mutations return a structured `result` (GraphQL payload).
- Most write tools support optional `debug=true` on errors (GraphQL codes + `correlation_id`).
- `extra_input` merges extra API keys (camelCase); keys that would duplicate primary arguments are ignored.
- **Destructive deletes** (`delete_pipe`, `delete_card`) use a two-step flow: first call returns a preview, then `confirm=true` after user approval.

### Pipefy IDs (type safety)

Which **form** each tool wants (slug vs `internal_id` vs uuid vs numeric id) is the canonical [Identifiers map](identifiers.md#field-references-slug-vs-internal_id); this section covers string-vs-int type safety and coercion.

Pipefy’s GraphQL API uses **string** IDs for pipes, phases, cards, and most other nodes.

- **Prefer string arguments** when calling tools (e.g. `card_id: "1332881010"`, `pipe_id: "306996634"`). This matches API responses (`get_pipe`, `get_card`, `create_card`, etc.).
- **Integer JSON values** (e.g. `1332881010` without quotes) are still accepted on many tools: they are **coerced to strings** before variables are sent to GraphQL, so behavior matches the API.
- **Validation:** empty strings, whitespace-only IDs, and non-positive numeric IDs are rejected with a clear tool error (no spurious `ValueError` from type mixing).
- **`delete_card`:** `card_id` follows the same rule — use a **string** (recommended) or a positive integer; the tool normalizes to a string for `getCard` / `deleteCard`. On success, `card_id` in the payload is a **string**.

---

## Pipe reads

| Tool | Role |
|------|------|
| `get_pipe` | Load pipe metadata (phases, fields, settings). Workflow `phases[]` include `cards_count`; start-form intake is via `start_form_fields` (start form is not in `phases[]`). |
| `get_start_form_fields` | Start-form fields for a pipe. |
| `get_phase_fields` | Fields for a phase — each includes `id`, `internal_id`, `uuid`. |
| `get_pipe_members` | List pipe members. |
| `get_labels` | List labels configured on the pipe (`id`, `name`). |
| `search_pipes` | Search pipes by name. |
| `get_phase_cards_count` | Native `Phase.cards_count` for one phase (fast scalar). Start-form count may be **0** while cards exist — pair with `get_phase_cards`. |
| `get_phase_cards` | Paginated cards in a phase (`Phase.cards`). Prefer over `get_cards` for phase-local inventory. |

## Card reads

| Tool | Role |
|------|------|
| `get_cards` | List cards in a pipe. Use `include_fields` for custom field name/value on each card. |
| `get_card` | Load a single card by ID. |
| `find_cards` | Search cards by title or field values. |

## Pipe building (structure & labels)

| Group | Tools | Notes |
|-------|-------|-------|
| Pipe | `create_pipe`, `update_pipe`, `delete_pipe`, `clone_pipe` | `delete_pipe`: two-step — preview first, then `confirm=true`. |
| Phase | `create_phase`, `update_phase`, `delete_phase` | `create_phase` `index`: 1-based insert among `get_pipe` workflow phases; omit to append. Prefer `1+` (not `0`). Index sets order only - not Connections / `allowed_phases` (UI-only). Destructive deletes: confirm with the user. |
| Phase transitions | `get_phase_allowed_move_targets` | Read-only; mirrors **Phase → Connections** (`cards_can_be_moved_to_phases`). Call before `move_card_to_phase`. Edges are configured in the Pipefy UI only. |
| Phase field | `create_phase_field`, `update_phase_field`, `delete_phase_field` | `field_type` maps to API `type`; `field_id` may be a slug or numeric ID. |
| Label | `create_label`, `update_label`, `delete_label` | `color` must be a hex string (e.g. `#FF0000`), not a name. |

## Cards (lifecycle & comments)

| Tool | Role |
|------|------|
| `create_card` | Create a card in the start form (default) or in a specific phase via optional `phase_id`; may use elicitation to ask the user for required fields mid-call. |
| `fill_card_phase_fields` | Fill phase-specific fields on a card; may use elicitation when available. |
| `add_card_comment` | Add a comment to a card. |
| `update_comment` | Update an existing comment. |
| `delete_comment` | Delete a comment (two-step: preview with `confirm=false`, then `confirm=true` after approval; `destructiveHint=True`). |
| `move_card_to_phase` | Move card to another phase. On failure for a required empty field, may return `success: false` naming that field; when a hide condition on the same required field is detected, the error may note that the field may be hidden while still required. |
| `update_card_field` | Single-field update (`updateCardField`). |
| `update_card` | Metadata (title, assignees, labels, due date) and/or multiple custom fields via `field_updates`. |
| `delete_card` | Two-step: default preview; `confirm=true` after explicit user confirmation. `card_id` is a **string** in the API; pass `"…"` or a coerced positive integer (see [Pipefy IDs](#pipefy-ids-type-safety)). |
| `upload_attachment_to_card` | Presigned URL + S3 PUT + `updateCardField` for **attachment** fields. **One file per call**: to attach multiple files, call the tool once per file. Provide **exactly one source**: `file_path` (a local filesystem path the MCP server reads; supports `~` expansion; local profile only) or `file_url` (an HTTPS URL the server downloads under an SSRF guard — http only if the deployment enables insecure URLs; works on any profile). On the hosted server `file_path` is rejected — pass `file_url`. `file_name` is inferred from the source basename when omitted (supply it explicitly when a URL has none); optional `content_type` is inferred from `file_name`. Either source is rejected above **100 MiB** before the presigned request. **`field_id` must be the field slug** (e.g. `document_upload`), not the uuid: using the uuid returns `RESOURCE_NOT_FOUND`. |
| `create_attachment_presigned_url` | Mints an S3 upload target (`upload_url`, `storage_path` object key, `expires_in_seconds`) for an org + `file_name`, **without transferring bytes** — for attaching a file the server can't read (a local file on the hosted profile, or bytes too large to inline). The client PUTs the file to `upload_url` within the expiry, then sets an attachment field to `[storage_path]` via `update_card_field` / `set_table_record_field_value` (store the key, never the url). Remote-safe. |

**Choosing card updates:** `update_card_field` = one field, full replacement. `update_card` + `field_updates` = several custom fields at once. `update_card` with attribute args = metadata (combinable with `field_updates`).

### Headless / agent clients

When elicitation is unavailable, `create_card` and `fill_card_phase_fields` still work but behave differently. That covers agents, CLIs, and SDK consumers, and also **the hosted server**, which serves `json_response=True` and so has no server-to-client back channel at any protocol revision:

1. The tool fetches the start-form or phase field definitions internally.
2. Provided `fields` are **filtered to editable field IDs only** — keys that do not match an editable field are silently discarded (no error).
3. The filtered dict is sent directly to the Pipefy API.

Because non-editable keys are dropped without warning, agents should discover fields first and pass all required values explicitly:

```
get_start_form_fields(pipe_id)   → learn field IDs, types, required flag
create_card(pipe_id, fields={…}) → supply every required field ID

get_pipe(pipe_id)                → phases[].id / cards_count for workflow inventory
create_card(
  pipe_id,
  phase_id="340012345",
  skip_elicitation=true,
  title="Seeded card",
  fields={…},
)                                → card created in that phase (fields via get_phase_fields + get_start_form_fields)

get_phase_fields(phase_id)                     → learn phase field IDs
fill_card_phase_fields(card_id, phase_id, fields={…}) → supply values
pipefy card fill <card_id> --phase <phase_id> --fields '{"…"}'  → CLI equivalent (non-interactive)
```

With `phase_id`, interactive clients may still elicit start-form fields when elicitation is supported; set `skip_elicitation=true` for agent workflows. When `fields` is non-empty, keys are filtered against both `get_phase_fields(phase_id)` and `get_start_form_fields(pipe_id)` so pipes that still require start-form values on `CreateCardInput` receive them alongside phase fields. Optional `title` is sent on `CreateCardInput` (no separate `update_card` on the happy path).

### `get_pipe` inventory fields

MCP tool results use the standard envelope; inventory fields live under the `pipe` object:

| JSON path | Meaning |
|-----------|---------|
| `pipe.start_form_fields` | Start-form field definitions (intake) |
| `pipe.phases[].id` | Workflow phase IDs (start form excluded) |
| `pipe.phases[].name` | Phase display name |
| `pipe.phases[].cards_count` | Native card count for that workflow phase |

CLI `pipefy pipe get <pipe_id> --json` returns the same GraphQL shape.

### Phase inventory (`get_phase_cards_count` / `get_phase_cards`)

Use these when you need per-phase totals or card lists without pipe-wide `CardSearch`:

| Tool | CLI | When to use |
|------|-----|-------------|
| `get_phase_cards_count` | `pipefy phase count <phase_id>` | Quick scalar; empty phases for seeding. |
| `get_phase_cards` | `pipefy phase cards <phase_id> --first 50 --after <cursor>` | Verify cards after create/move; paginate with `pageInfo.endCursor`. |

Discovery path: `get_pipe(pipe_id)` → `phases[].id` for workflow phases; omit `phase_id` on `create_card` for start-form intake.

```
get_phase_cards_count(phase_id="340012345")
get_phase_cards(phase_id="340012345", first=50, include_fields=true)
```

### Phase transitions (`get_phase_allowed_move_targets`)

Outbound moves are constrained by UI-configured connections — there is no API to add edges.

1. Resolve source phase: `get_card(card_id).current_phase.id` (or known `phase_id` before move).
2. `get_phase_allowed_move_targets(phase_id=<source>)` → `allowed_phases` (`{id, name}`).
3. `move_card_to_phase(card_id, destination_phase_id=<allowed id>)`.

CLI: `pipefy phase targets <phase_id> --json`.

Empty `allowed_phases` means no outbound transitions are configured in the UI.

## Field condition tools

Five tools read and configure conditional visibility on phase fields.

| Tool | Read-only | Role |
|------|-----------|------|
| `get_field_conditions` | Yes | Lists conditions for a phase (expressions, actions). |
| `get_field_condition` | Yes | Loads one condition by ID. |
| `create_field_condition` | No | Creates a rule: `phase_id`, `condition` (dict), `actions` (list of dicts), optional `extra_input`. Re-reads after create: `verified: true` when the rule exists on the requested phase; missing/wrong phase → `success: false` (delete the condition_id before recreating); if both verify reads fail, may return success with a warning (verification unavailable). Rejects `hide`/`hidden` on a `required=true` field before the mutation. |
| `update_field_condition` | No | Patches an existing rule: `condition_id` and at least one of `condition`, `actions`, or `extra_input`. When top-level `actions` is provided (not via `extra_input`), rejects `hide`/`hidden` on a `required=true` field before the mutation (best-effort if phase fields cannot be loaded). |
| `delete_field_condition` | No | Deletes a rule (`destructiveHint=True` — confirm with the user first). |

- `create_field_condition` maps to `createFieldConditionInput`: `phase_id`, `condition`, `actions`.
- Action entries use `phaseFieldId` with the target field's `internal_id` from `get_phase_fields` (not the slug `id`).
- The tool rejects an empty `condition`, an empty `expressions` list, and slug-like `phaseFieldId` values.
- Use `introspect_type('createFieldConditionInput')` / `UpdateFieldConditionInput` for optional keys in `extra_input`.
