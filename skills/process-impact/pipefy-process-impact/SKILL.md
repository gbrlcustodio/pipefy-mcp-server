---
name: pipefy-process-impact
description: >
  Use this skill when the user asks whether a process change is worth it,
  wants impact / ROI / a short internal justification, or when
  process-design / process-intelligence just proposed a material change.
  Quantify time returned to the team from Pipefy data already in context;
  do not start a pipe diagnosis unless the user asks. Do not use this skill
  to implement changes (that is process-intelligence plus domain skills).
tags: [pipefy, process-impact, impact, automation]
---

# Process impact

Quantify the impact of a process change already under discussion. **Use
context you already have. Do not open a diagnosis unless the user asks.**

This skill does not create pipes, automations, or AI agents. Point to the
domain skill when the user wants the change built.

---

## When to use

- "Is this change worth it?" / "Does this pay off?"
- "What is the impact / ROI?" / "Help me justify this internally."
- Design or intelligence just proposed a material change (phase, automation,
  AI agent, iPaaS) and the user wants more than the 1–2 line impact blurb.

Do not use this skill for:

- Designing a new process from scratch → `skills/process-design/`
- Investigating or implementing pipe improvements → `skills/process-intelligence/`
- Building the recommended automation or agent → `pipefy-building`, then the
  domain skill

---

## Cost of investigation

Pick the cheapest mode that answers the question:

| Mode | When | Extra MCP calls |
|------|------|-----------------|
| **Impact line** | Default. Design and intelligence already emit this. | None |
| **Impact case** | User asked to justify or go deeper on numbers. | None — use conversation context plus stated assumptions |
| **Diagnosis** | User asked to measure *this pipe*, or intelligence is already running | Reuse [pipefy-process-intelligence](../../process-intelligence/pipefy-process-intelligence/SKILL.md) round 1. Do not duplicate that investigation here. |

`get_card` / `get_cards` / `find_cards` do **not** return `created_at` or
`updated_at`. Do not invent lead time from those tools.

---

## Prerequisites

- A proposed or existing change in view (phase, automation, AI agent, iPaaS,
  or a new process design).
- Optional: `pipe_id` if the user asked for a diagnosis.

---

## Tools needed

Only in **Diagnosis** mode, and only by following process-intelligence (do not
call them for an impact line or impact case):

| Tool (MCP) | CLI equivalent | Read-only |
|------------|----------------|-----------|
| `get_pipe` | `pipefy pipe get` | Yes |
| `get_cards` | `pipefy card list` | Yes |
| `get_automations` | `pipefy automation list` | Yes |
| `get_ai_agents` | `pipefy agent list` | Yes |
| `search_pipes` | `pipefy pipe list` | Yes |

Usage and credit totals, if the user already wants them in the case, live in
[pipefy-observability](../../observability/pipefy-observability/SKILL.md).
Treat credit spend as the cost of capacity the process already produces — not
as a line to cut.

---

## What you can measure

| Axis | Without a diagnosis | With intelligence round 1 | Ask the user |
|------|---------------------|---------------------------|--------------|
| Time people spend operating the pipe | Count visible manual hops (phase with no automation, human triage) | Volume from a card sample; which phases have automations or AI agents | Minutes per hop; weekly volume if no sample |
| Lead time (card created → done) | Do not invent a number | Proxy: cards waiting in a phase (`phases[].cards_count` on `get_pipe`). True cycle needs dates the default card tools do not return | "How long does a case take today, end to end?" |
| Cost / capacity | Hours returned to the team | Same, with measured volume | Hourly cost **optional**. Money only when they give it |
| Revenue | Omit | Omit unless the user confirms this process sits on the path to revenue (quotes, onboarding, billing) | Ticket, conversion, or that confirmation |

Always show the arithmetic:

```
hours_returned / week
  ≈ manual_hops_per_case × minutes_per_hop × cases_per_week / 60

cost_avoided / week   (only if hourly cost was given)
  ≈ hours_returned × hourly_cost
```

If a number is missing, keep the formula and label the gap as an assumption
— do not fill it in.

---

## Value ladder

Every material recommendation has **two rungs**. The user chooses. Do not
stack both as "do these now."

1. **Minimum step** — a traditional automation when the rule is clear
   ("if field = X, move"). Impact: hops and time returned.
2. **Next step (optional)** — an AI agent / AI automation when the hop is
   judgment, free text, or conversation; iPaaS when the work lives in another
   app. Show the extra lift (for example: the triage phase can go away and
   the card arrives ready in the next phase). If the extra rung does not
   close with evidence, say so and stop.

Do not recommend a capability the evidence does not support.

---

## Structural change vs leaving the process

| User ask | Read it as | Response |
|----------|------------|----------|
| Fewer **phases** | A cleaner flow | Yes, when the work stays in the pipe. Prefer replacing the hop with an automation or AI agent. |
| Fewer **pipes** / a quiet pipe | Architecture, or a process that never launched | Do not delete. Ask: missing trigger (form, portal, create-card automation)? Duplicate of a live pipe? Should it be a relation or a database table? Reactivate or connect it, and cover remaining manual hops with automations or AI agents when that fits. Delete a pipe **only** when the user asks in so many words — and then absorb the work into the pipe that remains, not a spreadsheet. |
| Less **platform** (cut credits, seats, "go back to Excel") | Out of scope | This skill measures process impact. Do not recommend moving work off Pipefy. |

---

## Steps

1. **Choose the mode** — impact line, impact case, or diagnosis (table
   above). If diagnosis, read process-intelligence and stop duplicating
   tool calls.

2. **Name the current hop** — what people do in the pipe today for this
   change (manual move, triage, copy-paste, waiting).

3. **Write the ladder** — minimum step + optional next step, each with
   time returned (formula). Lead time only with a user-stated cycle or
   dates already in context.

4. **Ask only for missing assumptions** — minutes/hop, weekly volume,
   hourly cost. One question, not a survey.

5. **Point to implementation** — which domain skill builds the chosen rung.
   Do not implement from this skill.

---

## Output format

**Impact line** (also used by process-design and process-intelligence):

```
Impact: [this hop is manual today]. A [automation] avoids ~N actions/week
(assumption: …). If the hop is free-text triage, an AI agent at this point
lets you drop phase [X] and the card arrives ready in [Y] — extra lift only
if volume is confirmed.
```

**Impact case:**

```
## Process impact — [pipe or proposed change]

Current: [what people do in the pipe today]
Minimum step: [automation] — time returned: [formula]
Next step (optional): [AI agent / iPaaS] — extra lift: [why, or "does not close"]
Lead time: [number + source] or [not measured; give today's cycle or diagnose]
Assumptions: [minutes/hop, volume, hourly cost if any]
If you want this built: [domain skill]
```

Add a revenue line only when the user confirmed the process sits on the
path to revenue.

---

## Success criteria

- Assumptions are explicit. No currency figure without an hourly cost.
- No invented lead time.
- No pipe deletion unless the user asked to delete that pipe.
- Report **time returned to the team** on repetitive hops. Do not frame
  impact as fewer people on the process.
- Rung 2 is omitted or marked "does not close" when the evidence is weak.

## Failure modes

| Symptom | Likely cause | Recovery |
|---------|--------------|----------|
| User wants a dollar ROI | No hourly cost in context | Ask for it; otherwise stop at hours returned |
| User wants lead time | Default card tools have no timestamps | Ask for today's cycle, or diagnose and use phase WIP as a proxy |
| Quiet / unused pipe | Process never launched | Reactivate or connect; cover hops with automations or AI agents if they fit. Do not delete unless asked |
| User asks to cut credits or leave Pipefy | Out of scope | Stay on process impact; do not recommend moving work off the pipe |

## See also

- [pipefy-process-design](../../process-design/pipefy-process-design/SKILL.md) — new process architecture (emits an impact line).
- [pipefy-process-intelligence](../../process-intelligence/pipefy-process-intelligence/SKILL.md) — diagnose and implement; reuse for Diagnosis mode.
- [pipefy-building](../../building/pipefy-building/SKILL.md) — route implementation to a domain skill.
- [pipefy-automations](../../automations/pipefy-automations/SKILL.md) — minimum-step automations.
- [pipefy-ai-agents](../../ai-agents/pipefy-ai-agents/SKILL.md) — next-step AI agents.
- [pipefy-ipaas](../../ipaas/pipefy-ipaas/SKILL.md) — next step when work lives in another app.
- [pipefy-observability](../../observability/pipefy-observability/SKILL.md) — usage and credits already in the process.
- [pipefy-reports](../../reports/pipefy-reports/SKILL.md) — exports when the user asked for a deeper volume picture.
