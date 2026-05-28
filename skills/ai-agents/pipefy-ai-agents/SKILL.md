---
name: pipefy-ai-agents
description: >
  Use this skill when the user wants to create, read, update, delete,
  or troubleshoot AI agents (conversational agents with behaviors).
  Covers 7 MCP tools including pre-flight validation.
  For traditional automations and AI automations, see skills/automations/.
tags: [pipefy, ai-agents, behaviors, conversational]
---

# AI Agents

Conversational AI agents attached to pipes. Each agent has an agent-level instruction and 1–5 behaviors, each with its own trigger event, prompt, and actions. **7 MCP tools.**

For traditional automations and AI automations (prompt-driven), see [skills/automations/pipefy-automations/SKILL.md](../../automations/pipefy-automations/SKILL.md).

---

## Tools

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `get_ai_agents` | `pipefy agent list` | Yes | List AI agents for a pipe (`repo_uuid` = pipe UUID, not numeric `id`). |
| `get_ai_agent` | `pipefy agent get` | Yes | Full agent config including behaviors. |
| `create_ai_agent` | `pipefy agent create` | No | Create a new conversational agent. |
| `update_ai_agent` | `pipefy agent update` | No | **Full-replace** (not patch). Always send complete `behaviors`. |
| `delete_ai_agent` | `pipefy agent delete` | No | **(Two-step destructive)** |
| `toggle_ai_agent_status` | `pipefy agent toggle` | No | Enable/disable the agent (e.g. `--inactive`). |
| `validate_ai_agent_behaviors` | `pipefy agent validate-behaviors` | Yes | **Pre-flight check before create/update.** |

Execution logs live in [skills/observability/](../../observability/pipefy-observability/SKILL.md) (`get_ai_agent_logs`, `get_ai_agent_log_details`).

---

## Creation workflow (discover → validate → create → verify)

Never guess event IDs, phase IDs, action types, or field IDs.

### 1 — Get pipe metadata

Call `get_pipe(pipe_id)` and extract:

- `uuid` → use as `repo_uuid` in all AI-agent tools.
- `phases[].id` / `phases[].name` → needed for `move_card` actions.
- Fields via `get_start_form_fields(pipe_id)` and/or `get_phase_fields(phase_id)` → needed for `update_card` actions.

### 2 — Check existing agents

`get_ai_agents(repo_uuid)` to avoid duplicates. To modify an existing agent, use `update_ai_agent` (not create). For full config, use `get_ai_agent(uuid)`.

### 3 — Discover valid trigger events

`get_automation_events(pipe_id)`. Common events:

| Event (`event_id` value) | `event_params` required | Example |
|------------|-------------------------|---------|
| card_created | None | `{}` |
| card_moved | `{"to_phase_id":"<phase_id>"}` | Fires only when card enters that phase. |
| field_updated | `{"triggerFieldIds":["<field_id>", ...]}` | Fires only when those fields change. |
| manually_triggered | None | User clicks button on card. |

For `card_moved` and `field_updated`, you MUST include `event_params`. Omitting it makes the behavior fire on every occurrence.

### 4 — Discover valid action types

`get_automation_actions(pipe_id)`. Inside `actionsAttributes`:

| Action (`actionType` value) | `metadata` required |
|--------------|---------------------|
| update_card | `pipeId` + `fieldsAttributes` with `inputMode` |
| move_card | `destinationPhaseId` |
| create_card | `pipeId` + `fieldsAttributes` |
| create_connected_card | `pipeId` + `fieldsAttributes` (requires pipe relation) |

### 5 — Build the behavior dict

```json
{
  "name": "<descriptive name>",
  "event_id": "<from step 3>",
  "event_params": {},
  "actionParams": {
    "aiBehaviorParams": {
      "instruction": "<prompt for the AI when this event fires>",
      "actionsAttributes": [
        { "name": "<action label>", "actionType": "<from step 4>", "metadata": { } }
      ]
    }
  }
}
```

- Each behavior MUST have at least one action in `actionsAttributes`.
- **Maximum 5 behaviors per agent.**
- The MCP tool auto-injects `referenceId` and `%{action:<uuid>}` placeholders — do NOT generate these yourself.
- `inputMode: "fill_with_ai"` lets the AI decide the value. Omit `inputMode` and set `value` for fixed values.
- For `update_card`: set `destinationPhaseId: ""` when not moving the card.

#### Example identifiers (fictional)

Use real values from `get_pipe` / `get_start_form_fields` for your org. Placeholders below match unit-test fixtures in this repo. **The syntax matters** (`pipeId`, `fieldId`, `%{field:<internal_id>}`, `inputMode`) — **the example digits do not**; substitute each pipe's numeric `internal_id` and phase id.

| Role | Example value |
|------|----------------|
| Pipe (numeric repo id) | `987654321` |
| Field `internal_id` | `900000101` |
| Destination phase (`move_card`) | `900000201` |
| Target pipe (`create_card`) | `900000301` |

#### Metadata examples

```json
// update_card
{ "pipeId": "987654321", "destinationPhaseId": "", "fieldsAttributes": [{ "fieldId": "900000101", "inputMode": "fill_with_ai", "value": "" }] }

// move_card
{ "destinationPhaseId": "900000201", "pipeId": "", "fieldsAttributes": [] }

// create_card
{ "pipeId": "900000301", "fieldsAttributes": [{ "fieldId": "title", "inputMode": "fill_with_ai", "value": "" }] }
```

### 6 — Validate (recommended for complex behaviors)

`validate_ai_agent_behaviors(pipe_id, behaviors)` checks:
- Field IDs exist in the pipe
- Phase IDs exist
- Pipe relations exist for `create_connected_card`
- Action types are valid
- Behavior structure passes Pydantic validation
- Service-account membership on cross-pipe targets when `PIPEFY_SERVICE_ACCOUNT_IDS` is set
- Field IDs are checked against start-form and phase fields, accepting both slug `id` and numeric `internal_id`. Placeholders like `%{field:<slug>}` or `%{field:<internal_id>}` are validated but **not rewritten** at this step.

### 7 — Create the agent

`create_ai_agent` with `name`, `repo_uuid`, `instruction`, and `behaviors`. One-call creation is preferred — avoids partial agent shells. Agents are **active by default**.

On create/update, slug `fieldId` values are resolved to numeric `internal_id`, `%{field:<slug>}` is rewritten to `%{field:<internal_id>}`, and `referencedFieldIds` is auto-populated when applicable.

### 8 — Handle responses

- **Success with `agent_uuid`** → done.
- **Partial failure (UUID returned, behaviors rejected)** → call `update_ai_agent` with that UUID. Do NOT create a second agent.
- **Failure without UUID** → validation or API error. Trust the hint text in the enriched error.

### 9 — Verify

`get_ai_agent(uuid)` to confirm behaviors match expectations.

---

## Token normalization & slug resolution

Instructions accept five token aliases — all normalize to canonical `%{field:<internal_id>}`:

| Form | Behavior |
|------|----------|
| `%{<internal_id>}` | Canonical short form. |
| `{<internal_id>}` | Bare; auto-prefixed with `%`. |
| `{field:<internal_id>}` | Bare-with-prefix; auto-`%`. |
| `{field:<slug>}` | Bare slug; resolved to numeric when behavior action carries `pipeId`. |
| `%{field:<internal_id>}` | Canonical full form. |

`%{field:<slug>}` is rewritten to `%{field:<internal_id>}` when an action in the behavior supplies `pipeId`. If the Pipefy UI shows plain text instead of chips in token slots, the payload probably still has non-canonical tokens.

---

## Template params / placeholders

Per behavior you can pass `template_params` (or `placeholders`) with `str → str` values and use `{{name}}` in any string (instruction, metadata IDs, etc.). Optionally set `instruction_template` instead of `aiBehaviorParams.instruction` — the tool interpolates and writes the final instruction before the API call. These keys are stripped before validation.

```json
{
  "name": "Classify card",
  "event_id": "card_created",
  "instruction_template": "Read {{field_ref}} and classify the card.",
  "template_params": { "field_ref": "%{field:900000101}" },
  "actionParams": {
    "aiBehaviorParams": {
      "actionsAttributes": [
        {
          "name": "Fill classification",
          "actionType": "update_card",
          "metadata": { "pipeId": "{{pipe}}", "fieldsAttributes": [{ "fieldId": "{{class_field}}", "inputMode": "fill_with_ai", "value": "" }] }
        }
      ]
    }
  },
  "placeholders": { "pipe": "987654321", "class_field": "900000101" }
}
```

`template_params` and `placeholders` merge (placeholders wins on conflict).

---

## Naming differences (UI vs API)

| Pipefy UI | API / Tool field |
|-----------|------------------|
| Description (agent creation step 1) | `instruction` (agent-level) |
| Instruction / Prompt (per behavior) | `actionParams.aiBehaviorParams.instruction` |
| Pipe UUID | `repo_uuid` (from `get_pipe().uuid`, NOT the numeric `id`) |

---

## Success criteria

- `get_ai_agent` returns the agent with `status: active`.
- `validate_ai_agent_behaviors` reports no errors before creation.
- Agent appears in the Pipefy UI under the pipe's AI settings.

## Failure modes

- **`update_ai_agent` is full-replace, not patch.** Fetch existing behaviors with `get_ai_agent` first, merge, then update — otherwise existing behaviors are silently dropped.
- **Behavior save is all-or-nothing (`RECORD_NOT_SAVED`).** One invalid behavior rejects the entire list. The MCP tool auto-validates the payload on failure; if structurally correct, the error indicates a pipe-level restriction (not your payload). Inform the user this pipe does not support AI agent behaviors and suggest alternatives.
- **Partial-failure recovery.** If `create_ai_agent` returns a UUID but reports failure, call `update_ai_agent` with that UUID. Do NOT create a second agent.
- **Cross-pipe `PERMISSION_DENIED`.** Behaviors with `create_connected_card` or cross-pipe `create_card` require the service account to be a member of **both** source and destination pipes. `validate_ai_agent_behaviors` catches this when `PIPEFY_SERVICE_ACCOUNT_IDS` is set; otherwise the API returns bare `PERMISSION_DENIED`. Recovery: `get_pipe_members` + `invite_members` on the destination pipe.
- **Phase transition rule on `move_card`.** Destination must be reachable from the source phase (`cards_can_be_moved_to_phases`). Both `validate_ai_agent_behaviors` and `create_ai_agent` / `update_ai_agent` enrich this error with `valid_destinations` and a hint that transition rules are editable in the Pipefy UI only.
- **Maximum 5 behaviors per agent.** Adding a 6th rejects the whole save.
- **Ghost agents.** An agent listed by `get_ai_agents` may return "Agent not found" on `get_ai_agent` — a Pipefy backend artifact, persists across sessions, do not retry.
- **GraphQL error hints.** When a dedicated read tool returns permission-denied or not-found, the `error.message` may cite concrete tools (e.g. `"Use 'get_ai_agents' to list agents..."`). Trust the hint; don't improvise alternative flows.
- **Validation rejections.** Common issues: invalid `trigger_event`, prompt too long, missing required action config. Read the `errors` field per behavior.
- **`delete_ai_agent` first call returns preview.** Expected — show preview to user, then call with `confirm=true`.

## See also

- [skills/automations/pipefy-automations/SKILL.md](../../automations/pipefy-automations/SKILL.md) — traditional automations and AI automations (different from AI agents).
- [skills/observability/pipefy-observability/SKILL.md](../../observability/pipefy-observability/SKILL.md) — agent execution logs and credit usage.
- [skills/introspection/pipefy-introspection/SKILL.md](../../introspection/pipefy-introspection/SKILL.md) — Recipe 2 inspects full behavior config via `execute_graphql`.
