---
name: pipefy-pipes-and-cards
description: >
  Use this skill when the user wants to read, create, update, or delete
  pipes, phases, phase fields, labels, cards, comments, or field conditions.
  Covers 37 MCP tools for the core pipe and card lifecycle.
tags: [pipefy, pipes, cards, phases, fields, labels, comments, field-conditions]
---

# Pipes & Cards

Read, create, update, and delete pipes, phases, phase fields, labels, cards, attachments, and field conditions. **37 MCP tools.**

---

## Cross-cutting patterns

- **Field types** are not validated locally — use `introspect_type` (e.g., on `CreatePhaseFieldInput`) for allowed values.
- Most write tools support `debug=true` on errors (returns GraphQL codes + `correlation_id`).
- `extra_input` merges extra API keys (camelCase); keys that duplicate primary arguments are ignored.

---

## Pipe operations

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `get_pipe` | `pipefy pipe get <id>` | Yes | Fetch pipe metadata including phases and fields. |
| `search_pipes` | `pipefy pipe list` | Yes | Search by name pattern. |
| `create_pipe` | `pipefy pipe create` | No | Create a new pipe in the org. |
| `update_pipe` | `pipefy pipe update <id>` | No | Rename or change pipe settings. |
| `delete_pipe` | `pipefy pipe delete <id>` | No | **Two-step destructive.** |
| `clone_pipe` | `pipefy pipe clone <id>` | No | Clone an existing pipe. |

### Steps — create a pipe with phases

1. **Create the pipe:**

   MCP: `create_pipe name="Customer Onboarding" organization_id=123`

   CLI: `pipefy pipe create --name "Customer Onboarding" --org 123`

2. **Add phases** — call `create_phase` for each phase (see Phase section below).

3. **Add start form fields** — call `create_phase_field` on the start form phase.

---

## Phase operations

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `get_pipe` | `pipefy phase get <id>` | Yes | Phase metadata: use `get_pipe` (phases in the response) via MCP, or `pipefy phase get` on the CLI for a single phase. |
| `create_phase` | `pipefy phase create` | No | Add a phase to a pipe. |
| `update_phase` | `pipefy phase update <id>` | No | Rename, reorder, set done flag. |
| `delete_phase` | `pipefy phase delete <id>` | No | **Two-step destructive.** |

---

## Phase field operations

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `get_phase_fields` | `pipefy field list --phase <id>` | Yes | List fields on a phase. |
| `get_start_form_fields` | — | Yes | List start-form fields for card creation. |
| `create_phase_field` | `pipefy field create --phase <id>` | No | Add field to a phase. |
| `update_phase_field` | `pipefy field update <id>` | No | Rename, reorder, change required flag. |
| `delete_phase_field` | `pipefy field delete <id>` | No | **Two-step destructive.** |

**Discover field types:**

MCP: `introspect_type type_name="CreatePhaseFieldInput"`

This returns valid `type` enum values and their descriptions.

---

## Card operations

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `get_card` | `pipefy card get <id>` | Yes | Card data, fields, and comments. |
| `get_cards` | `pipefy card list --pipe <id>` | Yes | Paginated card list by pipe. |
| `find_cards` | `pipefy card find --pipe <id>` | Yes | Filter by a single field value. |
| `create_card` | `pipefy card create --pipe <id>` | No | **Always get start form fields first.** |
| `update_card` | `pipefy card update <id>` | No | Update title, assignee, due date, fields. |
| `move_card_to_phase` | `pipefy card move <id>` | No | Move a card to a different phase. |
| `delete_card` | `pipefy card delete <id>` | No | **Two-step destructive.** |
| `add_card_comment` | `pipefy card comment add <id>` | No | Add a text comment to a card. |

### Steps — create a card

1. **Get start form fields** (required — never skip):

   MCP: `get_start_form_fields pipe_id=67890`

   CLI: (use MCP or check pipe config)

2. **Create the card with fields:**

   MCP:
   ```
   create_card pipe_id=67890 title="My Card" fields_attributes='[{"field_id":"field_slug","field_value":"value"}]'
   ```

   CLI:
   ```bash
   pipefy card create --pipe 67890 --title "My Card" --fields '{"field_slug":"value"}'
   ```

3. **Report result** with card ID and link: `https://app.pipefy.com/open-cards/<CARD_ID>`

### Pagination for get_cards

```
get_cards pipe_id=67890 first=50 after=<endCursor>
```

Read `pageInfo.hasNextPage` and `pageInfo.endCursor` from the response; pass `after=<endCursor>` for the next page.

---

## Label operations

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `get_labels` | `pipefy label list --pipe <id>` | Yes | List pipe labels. |
| `create_label` | `pipefy label create` | No | Create a label with a color. |
| `update_label` | `pipefy label update <id>` | No | Rename or recolor. |
| `delete_label` | `pipefy label delete <id>` | No | **Two-step destructive.** |

---

## Field condition operations

| Tool (MCP) | CLI | Purpose |
|------------|-----|---------|
| `get_field_conditions` | — | List all field conditions on a phase. |
| `create_field_condition` | — | Create show/hide rule. |
| `update_field_condition` | — | Update condition action or rule. |
| `delete_field_condition` | — | **Two-step destructive.** |

---

## Success criteria

- Pipe and phases visible in Pipefy UI.
- `get_pipe` returns the new pipe ID and phases.
- Cards created via `create_card` appear in the pipe's first phase.

## Failure modes

- **`create_card` fails with missing required fields:** call `get_start_form_fields` first to discover required `field_id` values.
- **`create_phase_field` rejects type:** call `introspect_type type_name="CreatePhaseFieldInput"` to get valid values.
- **Delete fails with preview error:** expected — call without `confirm=true` first, show user the preview, then call with `confirm=true`.

## See also

- `skills/relations/` — link pipes and cards across workflows.
- `skills/automations/` — add automation rules to a pipe.
- `skills/introspection/` — discover field types and mutation signatures.
