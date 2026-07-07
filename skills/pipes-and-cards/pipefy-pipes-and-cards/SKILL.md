---
name: pipefy-pipes-and-cards
description: >
  Use this skill when the user wants to read, create, update, or delete
  pipes, phases, phase fields, labels, cards, comments, or field conditions.
  Covers 40 MCP tools for the core pipe and card lifecycle. Use the
  seed-pipe-across-phases workflow when populating empty phases for demos or QA.
tags: [pipefy, pipes, cards, phases, fields, labels, comments, field-conditions]
---

# Pipes & Cards

Read, create, update, and delete pipes, phases, phase fields, labels, cards, attachments, and field conditions. **40 MCP tools.**

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
| `get_phase_allowed_move_targets` | `pipefy phase targets <id>` | Yes | Valid destination phases before `move_card_to_phase` (UI-configured edges only). |
| `get_phase_cards_count` | `pipefy phase count <id>` | Yes | Native per-phase card count via `get_phase`. |
| `get_phase_cards` | `pipefy phase cards <id>` | Yes | Paginated cards in a phase (`--first`, `--after`, optional `--include-fields`). |

---

## Seed pipe across phases

Use this workflow to place at least one card in each workflow phase (demos, QA checklists, chaos pipes) **without** `execute_graphql`. Transition edges must already exist in the Pipefy UI.

### Tools needed

| Tool (MCP) | CLI | Read-only |
|------------|-----|-----------|
| `get_pipe` | `pipefy pipe get <pipe_id>` | Yes |
| `get_phase_cards_count` | `pipefy phase count <phase_id>` | Yes |
| `create_card` | `pipefy card create <pipe_id> --phase-id <id>` | No |
| `get_phase_cards` | `pipefy phase cards <phase_id>` | Yes |
| `get_phase_allowed_move_targets` | `pipefy phase targets <phase_id>` | Yes |
| `move_card_to_phase` | `pipefy card move <card_id> --phase <id>` | No |

### Steps

1. **Load phase IDs** — `get_pipe(pipe_id)` → collect `phases[].id` for workflow phases. Omit `phase_id` on `create_card` for start-form intake.

   MCP: `get_pipe pipe_id="306996634"`

   CLI: `pipefy pipe get 306996634 --json`

2. **Find empty phases** — for each candidate `phase_id`, call `get_phase_cards_count`. Target phases where `cards_count` is 0 (if the start form shows 0 but you suspect cards, call `get_phase_cards` before creating duplicates).

   MCP: `get_phase_cards_count phase_id="340012345"`

   CLI: `pipefy phase count 340012345 --json`

3. **Create cards in empty phases** — loop `create_card` with `phase_id` (and `skip_elicitation=true` for agent seeding). When `fields` is non-empty, keys are filtered via `get_phase_fields(phase_id)` and `get_start_form_fields(pipe_id)`.

   MCP:
   ```
   create_card pipe_id="306996634" phase_id="340012345" skip_elicitation=true title="Seeded"
   ```

   CLI:
   ```bash
   pipefy card create 306996634 --phase-id 340012345 --title "Seeded"
   ```

4. **Verify inventory** — `get_phase_cards(phase_id, first=50)` and confirm expected card IDs/titles.

   CLI: `pipefy phase cards 340012345 --json`

5. **Before moves** — on the card's current phase, `get_phase_allowed_move_targets` then `move_card_to_phase` only to an `allowed_phases[].id`.

   MCP: `get_phase_allowed_move_targets phase_id="<current_phase_id>"`

   CLI: `pipefy phase targets <current_phase_id> --json`

### Success criteria

- Every targeted phase reports `cards_count >= 1` (or `get_phase_cards` lists the seeded cards).
- Moves use only phases returned in `allowed_phases`.

### Failure modes

- **Empty `allowed_phases`:** configure **Phase → Connections** in the Pipefy UI; the API cannot add edges.
- **Unexpected empty count:** use `get_phase_cards` to list cards before creating duplicates.

---

## Phase field operations

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `get_phase_fields` | `pipefy field list --phase <id>` | Yes | List fields on a phase. |
| `get_start_form_fields` | `pipefy pipe start-form <pipe_id>` | Yes | List start-form fields for card creation. |
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
| `create_card` | `pipefy card create <pipe_id>` | No | Default: start form. Optional `--phase-id` / `phase_id` creates in that phase; interactive clients may elicit start-form fields unless `skip_elicitation=true`. |
| `fill_card_phase_fields` | `pipefy card fill <id> --phase <id>` | No | Fill phase fields non-interactively; filters to editable IDs. Uses `--fields` JSON object; for ad-hoc updates use `card update --field-updates` (JSON array). |
| `update_card` | `pipefy card update <id>` | No | Update title, assignee, due date, fields. |
| `move_card_to_phase` | `pipefy card move <id> --phase <id>` | No | Call `get_phase_allowed_move_targets` on the source phase first. |
| `delete_card` | `pipefy card delete <id>` | No | **Two-step destructive.** |
| `add_card_comment` | `pipefy card comment add <id>` | No | Add a text comment to a card. |

### Steps — create a card

1. **Get start form fields** (required — never skip):

   MCP: `get_start_form_fields pipe_id=67890`

   CLI: `pipefy pipe start-form 67890 --json`

2. **Create the card with fields:**

   MCP:
   ```
   create_card pipe_id=67890 title="My Card" fields_attributes='[{"field_id":"field_slug","field_value":"value"}]'
   ```

   CLI:
   ```bash
   pipefy card create 67890 --title "My Card" --fields '{"field_slug":"value"}'
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
