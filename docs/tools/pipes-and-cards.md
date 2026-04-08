# Pipes & Cards

Read, create, update, and delete pipes, phases, phase fields, labels, cards, and field conditions. **34 tools.**

## Cross-cutting patterns

- **Field types** are not validated locally — use `introspect_type` (e.g. on `CreatePhaseFieldInput`) for allowed values.
- Successful mutations return a structured `result` (GraphQL payload).
- Most write tools support optional `debug=true` on errors (GraphQL codes + `correlation_id`).
- `extra_input` merges extra API keys (camelCase); keys that would duplicate primary arguments are ignored.
- **Destructive deletes** (`delete_pipe`, `delete_card`) use a two-step flow: first call returns a preview, then `confirm=true` after user approval.

### Pipefy IDs (type safety)

Pipefy’s GraphQL API uses **string** IDs for pipes, phases, cards, and most other nodes.

- **Prefer string arguments** when calling tools (e.g. `card_id: "1332881010"`, `pipe_id: "306996634"`). This matches API responses (`get_pipe`, `get_card`, `create_card`, etc.).
- **Integer JSON values** (e.g. `1332881010` without quotes) are still accepted on many tools: they are **coerced to strings** before variables are sent to GraphQL, so behavior matches the API.
- **Validation:** empty strings, whitespace-only IDs, and non-positive numeric IDs are rejected with a clear tool error (no spurious `ValueError` from type mixing).
- **`delete_card`:** `card_id` follows the same rule — use a **string** (recommended) or a positive integer; the tool normalizes to a string for `getCard` / `deleteCard`. On success, `card_id` in the payload is a **string**.

---

## Pipe reads

| Tool | Role |
|------|------|
| `get_pipe` | Load pipe metadata (phases, fields, settings). |
| `get_start_form_fields` | Start-form fields for a pipe. |
| `get_phase_fields` | Fields for a phase — each includes `id`, `internal_id`, `uuid`. |
| `get_pipe_members` | List pipe members. |
| `search_pipes` | Search pipes by name. |

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
| Phase | `create_phase`, `update_phase`, `delete_phase` | Destructive deletes: confirm with the user. |
| Phase field | `create_phase_field`, `update_phase_field`, `delete_phase_field` | `field_type` maps to API `type`; `field_id` may be a slug or numeric ID. |
| Label | `create_label`, `update_label`, `delete_label` | `color` must be a hex string (e.g. `#FF0000`), not a name. |

## Cards (lifecycle & comments)

| Tool | Role |
|------|------|
| `create_card` | Create a card; may use elicitation to ask the user for required fields mid-call. |
| `add_card_comment` | Add a comment to a card. |
| `update_comment` | Update an existing comment. |
| `delete_comment` | Delete a comment. |
| `move_card_to_phase` | Move card to another phase. |
| `update_card_field` | Single-field update (`updateCardField`). |
| `update_card` | Metadata (title, assignees, labels, due date) and/or multiple custom fields via `field_updates`. |
| `delete_card` | Two-step: default preview; `confirm=true` after explicit user confirmation. `card_id` is a **string** in the API; pass `"…"` or a coerced positive integer (see [Pipefy IDs](#pipefy-ids-type-safety)). |
| `upload_attachment_to_card` | Presigned URL + S3 PUT + `updateCardField` for **attachment** fields. **One file per call** — to attach multiple files, call the tool once per file. Exactly one of `file_url` or `file_content_base64`; optional `content_type` (inferred from `file_name` if omitted). **`field_id` must be the field slug** (e.g. `document_upload`), not the uuid — using the uuid returns `RESOURCE_NOT_FOUND`. |

**Choosing card updates:** `update_card_field` = one field, full replacement. `update_card` + `field_updates` = several custom fields at once. `update_card` with attribute args = metadata (combinable with `field_updates`).

## Field condition tools

Three tools configure conditional visibility on phase fields.

| Tool | Read-only | Role |
|------|-----------|------|
| `create_field_condition` | No | Creates a rule: `phase_id`, `condition` (dict), `actions` (list of dicts), optional `extra_input`. |
| `update_field_condition` | No | Patches an existing rule: `condition_id` and at least one of `condition`, `actions`, or `extra_input`. |
| `delete_field_condition` | No | Deletes a rule (`destructiveHint=True` — confirm with the user first). |

- `create_field_condition` maps to `createFieldConditionInput`: `phase_id`, `condition`, `actions`.
- Action entries use `phaseFieldId` with the target field's `internal_id` from `get_phase_fields` (not the slug `id`).
- The tool rejects an empty `condition`, an empty `expressions` list, and slug-like `phaseFieldId` values.
- Use `introspect_type('createFieldConditionInput')` / `UpdateFieldConditionInput` for optional keys in `extra_input`.
