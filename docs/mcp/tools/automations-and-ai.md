# Automations & AI

Traditional automations (if/then rules) and AI-powered automations and agents. **23 tools.** (Execution logs, usage exports, and credit dashboards are in [Observability](observability.md).)

---

## Traditional automations (rules engine)

Ten tools manage Pipefy traditional automations: if/then rules bound to a pipe via the standard GraphQL API.

**Tip:** For **send-a-task** rules (`send_a_task` action), use `create_send_task_automation` (pipe, trigger, task title, recipients) instead of hand-building `action_params.taskParams` on `create_automation`. For other actions, call `get_automation_events` (global event catalog) and `get_automation_actions` with the target pipe (`repoId`) before `create_automation` to pick valid `trigger_id` / `action_id` values. Writes accept optional `extra_input` (top-level keys are snake_case, e.g. `action_params`, `event_params`; mirror `get_automation` output) and `debug=true` on errors.

| Tool | Read-only | Role |
|------|-----------|------|
| `get_automation` | Yes | Loads one rule by ID (trigger, actions, `active`). |
| `get_automations` | Yes | Lists rules; optional `organization_id` and/or `pipe_id`. |
| `get_automation_actions` | Yes | Catalog of action types for a pipe (IDs and field metadata). |
| `get_automation_events` | Yes | Catalog of trigger event definitions (global list; tool still takes `pipe_id` for context). |
| `get_automation_event_attributes` | Yes | **Event-scoped only** (today: one token). Full `field_map.value` list: see [Common value tokens](#common-value-tokens-copy_from) below. |
| `simulate_automation` | Yes | Runs a dry-run simulation for an automation with a payload (see tool docstring). |
| `create_automation` | No | Creates a rule: `pipe_id`, `name`, `trigger_id`, `action_id`; `active` defaults to true. Set `active: false` to create disabled. |
| `create_send_task_automation` | No | Creates a send-a-task automation (`pipe_id`, trigger, task title, recipients). Created active; disable via `update_automation`. |
| `update_automation` | No | Patches a rule via `extra_input` (`UpdateAutomationInput` fields). |
| `delete_automation` | No | Permanently deletes a rule (`destructiveHint=True` — confirm with the user first). |

### Traditional automation: `field_map` and dynamic values

Use action `update_card_field` when a rule should **stamp or copy values onto the triggering card** (for example, set a datetime field when a card is created). Do **not** use the MCP tool `update_card_field` for this — that tool updates one card field by **slug** in a single call. Automations use numeric `fieldId` values inside `extra_input.action_params.field_map`.

**`get_automation_actions` catalog gap:** for action `update_card_field`, `acceptedParameters` lists only `fields_map_order` and `card_id`. The API still requires `field_map` in `action_params`; shape and tokens are documented here and in the `create_automation` tool docstring.

#### Example: `card_created` → stamp execution datetime

Discover the destination field’s `internal_id` with `get_start_form_fields(pipe_id)` and/or `get_phase_fields(phase_id)` (use digits only in `fieldId`, not slug).

```json
{
  "pipe_id": "<pipe_id>",
  "name": "Stamp execution time on new cards",
  "trigger_id": "card_created",
  "action_id": "update_card_field",
  "active": false,
  "extra_input": {
    "action_params": {
      "card_id": "%{id}",
      "field_map": [
        {
          "fieldId": "<destination_internal_id>",
          "inputMode": "copy_from",
          "value": "%{automation_event_execution_datetime}"
        }
      ],
      "fields_map_order": ["<destination_internal_id>"]
    }
  }
}
```

| `field_map[]` key | Type | Meaning |
| --- | --- | --- |
| `fieldId` | string of digits | Destination field `internal_id` (`fields.id`) |
| `inputMode` | `copy_from` \| `fixed_value` \| `fill_with_ai` | How `value` is interpreted |
| `value` | string | Literal, or `%{…}` template when `inputMode` is `copy_from` |

Also set `action_params.card_id` to `"%{id}"` for the triggering card. `fields_map_order` is an array of the same destination `internal_id` strings as in `field_map`.

#### Common `value` tokens (`copy_from`)

| Token | Meaning |
| --- | --- |
| `%{id}` | Triggering card id (use in `card_id`, not only in `value`) |
| `%{title}` | Card title |
| `%{created_at}` | Card creation timestamp |
| `%{finished_at}` | Card finished timestamp |
| `%{due_date}` | Card due date |
| `%{current_phase}` | Current phase name |
| `%{assignees}` | Assignee list |
| `%{labels}` | Card labels |
| `%{created_by}` | Card creator |
| `%{automation_event_execution_datetime}` | Automation run timestamp (only token in `get_automation_event_attributes`) |
| `%{<internal_id>}` | Copy value from another field on the card (digits only, e.g. `%{429659034}`) |

Relative date ops (e.g. `%{created_at|plus:86400}`) are supported at runtime; see Pipefy's automation docs.

Official **event-scoped** catalog only: `get_automation_event_attributes` (MCP) or `pipefy automation event-attributes` (CLI) — today returns **one row** (`automation_event_execution_datetime`). See also [Automation Event Attributes](https://developers.pipefy.com/reference/automation-event-attributes). For the full set above, use this table, the `create_automation` docstring, or `get_automation` on an existing rule.

#### Slug vs `internal_id`

Full cross-tool identifier map: [identifiers.md](identifiers.md#field-references-slug-vs-internal_id).

| Surface | Field identifier |
| --- | --- |
| MCP `update_card_field` (`field_id` arg) | **slug** (`id` on field rows from `get_phase_fields`) |
| Traditional automation `field_map[].fieldId` | **numeric `internal_id`** |
| AI automation prompt `%{…}` | **numeric `internal_id`** (separate feature) |

Using a slug in `fieldId` typically yields `INTERNAL_SERVER_ERROR` on create; a wrong numeric id may fail silently at runtime (field not updated).

#### `field_map` preflight on `create_automation`

Before the GraphQL mutation, **`create_automation` only** validates each `field_map[].fieldId` against numeric `internal_id` values on the action pipe (`action_repo_id`, default `pipe_id`). Unknown ids and slug-shaped values return `success: false` with the offending `fieldId` and pointers to `get_start_form_fields` / `get_phase_fields`. `update_automation` does not run this check. Upstream field-load failures are skipped so transient API errors do not block creates.

#### Move-transition preflight on `create_automation`

For `card_moved` + `move_single_card`, when `extra_input` includes source and destination phase ids, `create_automation` rejects impossible transitions before GraphQL (same transition data as `move_card_to_phase`). The error is a **text** message listing allowed destination phases; there is no `valid_destinations` field on the automation error envelope. Recovery: parse allowed phases from the message or call `get_phase_allowed_move_targets` on the source phase id.

#### Recommended workflow

1. **Discover** — `get_automation_events(pipe_id)`, `get_automation_actions(pipe_id)`, `get_automation_event_attributes()` for official `field_map` tokens; field ids via `get_start_form_fields` / `get_phase_fields`.
2. **Create disabled** — `create_automation` with `active: false` and the `extra_input` payload above.
3. **Verify** — `get_automation(automation_id)` and confirm `action_params.field_map` round-trip.
4. **Enable** — `update_automation` with `extra_input: { "active": true }`.

---

## AI automations

AI automations are separate from traditional rules above. They are prompt-driven (`generate_with_ai`) and go through the same public `createAutomation` / `updateAutomation` mutations as traditional rules, using the session's normal auth. No service-account credentials are required.

| Tool | Read-only | Role |
|------|-----------|------|
| `create_ai_automation` | No | Prompt-driven automation writing to one or more card fields (AI must be enabled on the pipe). |
| `update_ai_automation` | No | Change name, `active`, prompt, `field_ids`, or `condition`. |
| `get_ai_automation` | Yes | Loads one AI automation by id (same GraphQL read path as `get_automation`). |
| `get_ai_automations` | Yes | Lists **only** `generate_with_ai` automations for the pipe (optional org resolution). |
| `delete_ai_automation` | No | Permanently deletes an AI automation (`destructiveHint=True` — two-step confirm). |
| `validate_ai_automation_prompt` | Yes | Pre-flight validation: field refs in the prompt, `field_ids`, optional `event_id`, and `pipe.preferences.aiAgentsEnabled`. |

### `create_ai_automation`: `condition` (contract)

On **create**, if the caller omits `condition`, the MCP layer supplies `DEFAULT_CONDITION` (see `CreateAiAutomationInput` in `pipefy_mcp.models.ai_automation`) so Pipefy always receives an explicit condition object. Pass a `condition` dict to override. On **`update_ai_automation`**, omit `condition` to leave the existing rule unchanged; pass a dict to replace it.

## AI agents

| Tool | Read-only | Role |
|------|-----------|------|
| `create_ai_agent` | No | Creates and configures an AI agent with `instruction` (= Pipefy UI "Description") and 1–5 `behaviors` in one call. `repo_uuid` is the pipe UUID from `get_pipe`. Optional: `data_source_ids`. |
| `update_ai_agent` | No | Replaces full agent config; send the complete `behaviors` list (1-5). |
| `toggle_ai_agent_status` | No | Enable/disable without resending configuration. |

**Tip:** Pipefy UI **Description** maps to the API/tool field `instruction` (agent-level purpose). The per-behavior prompt in the UI maps to `actionParams.aiBehaviorParams.instruction` on each behavior (behavior-level).

**Tip:** For `create_ai_agent` / `update_ai_agent`, each behavior must include `actionParams.aiBehaviorParams.actionsAttributes` with **at least one** action. The API returns *"The instructions must contain at least 1 action"* if this list is missing or empty.

**Discovery workflow** — call these tools before `create_ai_agent`:

1. `get_pipe(pipe_id)` → get the pipe `uuid` (use as `repo_uuid`) and its phase IDs.
2. `get_ai_agents(repo_uuid)` → check existing agents to avoid duplicates.
3. `get_automation_events(pipe_id)` → pick a valid `event_id` for the behavior trigger.
4. `get_automation_actions(pipe_id)` → find available action types for `actionsAttributes`.

### Behavior dict shape

```json
{
  "name": "When card is created: move to Doing",
  "event_id": "card_created",
  "actionParams": {
    "aiBehaviorParams": {
      "instruction": "Analyze the card and summarize key points.",
      "actionsAttributes": [
        {
          "name": "Move to Doing",
          "actionType": "move_card",
          "metadata": { "destinationPhaseId": "<phase_id>" }
        }
      ]
    }
  }
}
```

### Known `actionType` values

| `actionType` | Required `metadata` |
|---|---|
| `move_card` | `{ "destinationPhaseId": "<phase_id>" }` |
| `update_card` | `{ "pipeId": "<pipe_id>", "fieldsAttributes": [{ "fieldId": "...", "inputMode": "fill_with_ai", "value": "" }] }` |
| `create_card` | `{ "pipeId": "<pipe_id>", "fieldsAttributes": [...] }` |
| `create_connected_card` | `{ "pipeId": "<pipe_id>", "fieldsAttributes": [...] }` |
| `create_table_record` | `{ "tableId": "<table_id>", "fieldsAttributes": [...] }` (`pipeId` not required; MCP does not check table `fieldId` values against the pipe — use `get_table` / `get_table_record`.) |
| `send_email_template` | `{ "emailTemplateId": "<template_id>" }` (optional: `allowTemplateModifications` boolean; MCP does not verify that the template ID exists.) |

Optional inside `actionParams.aiBehaviorParams`:

- **`capabilitiesAttributes`** — list of capability entries, each exactly `{ "capabilityType": "<type>", "enabled": true|false }`. Both keys are required and no other keys are accepted; legacy shapes (bare string lists, `{ "type": ... }`) are rejected. Common `capabilityType` values: `advanced_ocr` (product name IDP / Intelligent Document Processing), `math_operations` (Calculations & Analysis), `web_search`, `web_scraping`, `max_effort`. `capabilityType` is not checked against a fixed set — any value passes through and the API validates the enum on write. Validation checks shape only, not plan/feature entitlement — a capability may still require organization-level enablement to take effect.
- **`providerId`** / **`systemProviderId`** — select the behavior's LLM provider; set at most one (reads resolve a single active provider). Discover IDs with `get_llm_providers` (see [LLM providers](llm-providers.md)): use `providerId` for a custom (`byom`) provider and `systemProviderId` for a Pipefy-managed (`system`) one. IDs are also visible in the organization's AI settings in the Pipefy UI.

### Optional `eventParams` (trigger filters)

| `event_id` | `eventParams` key | Purpose |
|---|---|---|
| `field_updated` | `triggerFieldIds` | Fire only when specific fields change |
| `card_moved` | `to_phase_id` | Fire only when card moves to a specific phase |

### AI Agent read & delete

Use `get_ai_agents` with the pipe's `uuid` (same as `repo_uuid`) before `create_ai_agent` to avoid duplicates.

| Tool | Read-only | Role |
|------|-----------|------|
| `get_ai_agent` | Yes | Loads one agent by UUID: name, instruction, behaviors. |
| `get_ai_agents` | Yes | Lists agents for a pipe (`repo_uuid` = pipe UUID). |
| `validate_ai_agent_behaviors` | Yes | Dry-runs behaviors against a pipe (fields, phases, relations); use before create/update. |
| `delete_ai_agent` | No | Permanently deletes an agent (`destructiveHint=True` — confirm with the user first). |

---

## Execution logs & usage

For **AI agent run history**, **traditional automation logs**, **org-level usage**, and **credit / export** tooling, use the observability tools. See [Observability](observability.md) for how `repo_uuid`, `repo_id`, and `automation_id` differ and for recommended call order (`get_automation_logs_by_repo` vs `get_automation_logs`).
