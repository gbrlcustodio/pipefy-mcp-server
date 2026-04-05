# Automations & AI

Traditional automations (if/then rules) and AI-powered automations and agents. **16 tools.**

---

## Traditional automations (rules engine)

Seven tools manage Pipefy traditional automations: if/then rules bound to a pipe via the standard GraphQL API.

**Tip:** Call `get_automation_events` (global event catalog) and `get_automation_actions` with the target pipe (`repoId`) before `create_automation` to pick valid `trigger_id` / `action_id` values. Writes accept optional `extra_input` (camelCase API keys) and `debug=true` on errors.

| Tool | Read-only | Role |
|------|-----------|------|
| `get_automation` | Yes | Loads one rule by ID (trigger, actions, `active`). |
| `get_automations` | Yes | Lists rules; optional `organization_id` and/or `pipe_id`. |
| `get_automation_actions` | Yes | Catalog of action types for a pipe (IDs and field metadata). |
| `get_automation_events` | Yes | Catalog of trigger event definitions (global list; tool still takes `pipe_id` for context). |
| `create_automation` | No | Creates a rule: `pipe_id`, `name`, `trigger_id`, `action_id`; `active` defaults to true. Set `active: false` to create disabled. |
| `update_automation` | No | Patches a rule via `extra_input` (`UpdateAutomationInput` fields). |
| `delete_automation` | No | Permanently deletes a rule (`destructiveHint=True` — confirm with the user first). |

---

## AI automations & agents

AI automations are separate from traditional rules above. They are prompt-driven and use the internal API.

| Tool | Role |
|------|------|
| `create_ai_automation` | Prompt-driven automation writing to one or more card fields (AI must be enabled on the pipe). |
| `update_ai_automation` | Change name, `active`, prompt, `field_ids`, or `condition`. |
| `create_ai_agent` | Creates and configures an AI agent with `instruction` (= Pipefy UI "Description") and 1–5 `behaviors` in one call. `repo_uuid` is the pipe UUID from `get_pipe`. Optional: `data_source_ids`. |
| `update_ai_agent` | Replaces full agent config; send the complete `behaviors` list (1-5). |
| `toggle_ai_agent_status` | Enable/disable without resending configuration. |

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
| `delete_ai_agent` | No | Permanently deletes an agent (`destructiveHint=True` — confirm with the user first). |

---

## Execution logs & usage

For **AI agent run history**, **traditional automation logs**, **org-level usage**, and **credit / export** tooling, use the observability tools. See [Observability](observability.md) for how `repo_uuid`, `repo_id`, and `automation_id` differ and for recommended call order (`get_automation_logs_by_repo` vs `get_automation_logs`).
