---
name: pipefy-process-intelligence
description: >
  Use this skill when the user wants to analyze an existing pipe for
  improvement opportunities — automation gaps, manual bottlenecks,
  missing AI agents, field conditions, or adjacent processes. Acts as
  a process analyst: investigates, diagnoses, and improves the pipe
  in progressive rounds — each round delivers visible results.
tags: [pipefy, process-intelligence, optimization, automation, analysis]
---

# Process Intelligence

Analyze existing pipes for improvement opportunities and implement them progressively. **Investigate immediately. Diagnose with data. Improve progressively.**

---

## When to use

The user asks to analyze or improve an existing process:
- "Analyze my pipe"
- "How can I improve this process?"
- "Is this pipe optimized?"
- "Where are the bottlenecks?"

**Not for:** designing a new process from scratch → use `skills/process-design/`.
Justifying a change with numbers only (no implementation) → use `skills/process-impact/`.

---

## Prerequisites

- Pipe ID or name is known (or searchable via `search_pipes`).
- Read access to the pipe's cards and phase data.

---

## Steps — investigation (Round 1)

1. **Get pipe structure:**

   MCP: `get_pipe pipe_id=<id>`

   Capture: phases, field count per phase, automation count.

2. **Sample recent cards** (last 30–50):

   MCP: `get_cards pipe_id=<id> first=50 include_fields=true`

   Look for: stale cards (no updates), cards stuck in early phases, phases with 0 cards.

3. **Check automations:**

   MCP: `get_automations pipe_id=<id>`

   Look for: phases with no automations (manual handoffs), repeated manual steps.

4. **Check AI configuration:**

   MCP: `get_ai_agents repo_uuid=<PIPE_UUID>`

   Look for: no AI agents despite manual categorization or triage patterns.

---

## Diagnosis framework

| Signal | Opportunity |
|--------|-------------|
| Cards stuck in a phase for >7 days | Add due date field + overdue automation |
| Phase transitions always done by same person | Automate the transition condition |
| Fields never filled in certain phases | Remove or make optional |
| Same comment posted repeatedly | AI agent to auto-post based on trigger |
| No automation between intake and first action | Add "notify assignee" automation on card creation |
| Large field count on start form | Move optional fields to later phases |
| Phases with 0 cards over 90 days | Merge into a neighboring phase, or replace the hop with an automation or AI agent. Do not treat an empty phase as a reason to delete the pipe. |

---

## Steps — improvement (Round 2+)

Each round focuses on 1–2 improvements; report results before proceeding.

**Example: add an overdue automation**

1. Identify the stalled phase and threshold (e.g., "Under Review" > 3 days).
2. Check automation events: `get_automation_events`
3. Create the automation:

   MCP: `create_automation pipe_id=<id> name="Overdue Alert" trigger_event="card_overdue" actions='[{"type":"send_email","to":"assignee"}]'`

4. Report: "Added overdue automation to 'Under Review' phase — triggers after 3 days and emails the assignee."

**Example: add a field condition**

1. Identify a field that should only show when another field has a specific value.
2. Create the condition:

   MCP: `create_field_condition pipe_id=<id> phase_id=<phase_id> action="show" when='{"field_id":"<f1>","value":"Yes"}' fields='["<f2>"]'`

---

## Output format per round

```
## Analysis — [Pipe Name]

### Findings
- [Finding 1]: [evidence from tool calls]
- [Finding 2]: ...

### Implemented this round
- [Change 1]: [tool called + result]

### Impact
- Minimum step: [automation already done or proposed]
- Next step (optional): [AI agent / iPaaS extra lift, or "does not close"]
- Time returned: [formula or qualitative]. Lead time only if this round already has dates.

### Next round (if approved)
- [Opportunity]: [proposed action]
```

Keep Impact to 1–2 lines unless the user asked for a fuller case — then read
[pipefy-process-impact](../../process-impact/pipefy-process-impact/SKILL.md).
Do not recommend deleting a pipe. Do not invent volume, hourly cost, or lead
time.

---

## Success criteria

- Each round produces a concrete visible change (new automation, field condition, phase cleanup).
- Card throughput improves in the affected phase within the next sprint.
- No improvement causes a regression (verify with `get_pipe` and `get_cards` after each round).

## Failure modes

- **`get_cards` returns empty:** pipe may have no cards yet — analyze structure only. Recommend standing up intake (start form, portal, or an automation that creates cards) rather than removing the pipe.
- **`create_automation` fails with unknown event:** use `get_automation_events` to list valid triggers.
- **User pushes back on automation:** explain what the automation does in plain language before creating.

## See also

- [pipefy-process-impact](../../process-impact/pipefy-process-impact/SKILL.md) — fuller justification; this skill only emits the Impact blurb per round.
- `skills/automations/` — detailed automation creation guide.
- `skills/ai-agents/` — add conversational agents for user-facing automation.
- `skills/observability/` — check credit and execution data to quantify improvement impact.
