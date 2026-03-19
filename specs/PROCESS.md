# Spec-Driven Development Process

A lightweight, spec-first workflow for AI-assisted development. Humans remain gatekeepers at every step — the AI never advances the process on its own.

## Overview

```
0. Create PRD  ──→  1. Create Spec  ──→  2. Review Spec  ──→  3. Generate Tasks
                           │                                         │
                           └─ (captures decisions) ──────────────────┘
                                                                     │
       ┌─────────────────────────────────────────────────────────────┘
       ▼
4. Review Tasks  ──→  5. Develop (one sub-task at a time)  ──→  6. Spec Sync  ──→  7. Done
                             │
                             └─ (captures decisions inline)
```

Decisions are captured **within** each step — not as a separate step. The `/record-decision` command exists as a standalone fallback for ad-hoc decisions (e.g., after a team discussion outside the AI workflow).

Every transition requires an explicit human action — running a command, reviewing output, or saying "yes" to proceed.

## Directory Structure

Each capability lives in its own folder under `specs/`:

```
specs/
├── PROCESS.md               # This file — workflow guide
└── <capability-name>/
    ├── prd-<capability-name>.md    # Step 0: intake document (goals, user stories)
    ├── spec-<capability-name>.md   # Step 1: formal specification (requirements + scenarios)
    ├── decisions/                  # Architecture Decision Records (ADRs)
    │   ├── 001-approach.md
    │   └── 002-trade-off.md
    └── tasks/
        └── tasks-<capability-name>.md  # Step 2: implementation task list
```

## Step-by-Step

### Step 0: Create PRD

**Command:** `/create-prd`

The user brings context — business needs, strategic direction, user problems, or reference documents — and works with the AI to produce a Product Requirements Document. The PRD captures the "what" and "why" at a high level: goals, user stories, functional requirements, non-goals, and open questions.

**What gets created:**
- `specs/<capability>/prd-<capability>.md`
- Empty `specs/<capability>/decisions/` directory
- Empty `specs/<capability>/tasks/` directory

**Human gate:** Review the PRD. Refine goals, user stories, and requirements until they accurately reflect what you want to build. The PRD is the intake artifact — it feeds the spec in the next step.

---

### Step 1: Create Spec

**Command:** `/create-spec`

Using the PRD (`specs/<capability>/prd-<capability>.md`) as input, the AI transforms high-level requirements into a formal specification with Gherkin-like scenarios. It may ask additional clarifying questions to fill gaps the PRD didn't cover.

**What gets created:**
- `specs/<capability>/spec-<capability>.md` (alongside the existing PRD)

**Human gate:** Review the generated spec. Adjust requirements and scenarios until they accurately describe what you want built. The spec is your contract — take the time to get it right.

**Decisions:** If significant technical decisions emerged during the Q&A (e.g., choosing an approach, ruling out alternatives), the AI drafts ADRs and presents them for your approval before saving.

---

### Step 2: Generate Tasks

**Command:** `/generate-tasks`

Point the AI to a spec. It analyzes requirements, scenarios, and any ADRs, then generates a task breakdown.

**What gets created:**
- `specs/<capability>/tasks/tasks-<capability>.md`

**Human gate:** The AI generates high-level tasks first and waits for "LGTM" before breaking them into detailed sub-tasks. Review both levels before proceeding.

**Decisions:** If the task breakdown revealed architectural decisions (e.g., new service vs. extending existing, API contract choices), the AI drafts ADRs and presents them for your approval.

---

### Step 3: Develop

**Command:** `/task-development`

Point the AI to the task list. It works through sub-tasks one at a time, pausing after each for your approval.

**Human gate:** After each sub-task, the AI stops and waits for "yes" or "y" before continuing. Review the implementation, run tests, and verify before approving.

**During development, the AI will:**
- Read the spec and ADRs before starting
- Flag any spec divergence immediately
- Draft ADRs inline when significant technical decisions arise, and present them for your approval
- Suggest `/update-spec` if requirements need to change

---

### Step 4: Update Spec (as needed)

**Command:** `/update-spec`

When requirements change — from business input, implementation discoveries, or ADRs — update the spec.

**What gets modified:**
- `specs/<capability>/spec-<capability>.md` (in place)

**Human gate:** The AI shows a "spec delta" (before/after) for review before applying changes. It also flags any tasks that may be impacted but does not modify them automatically.

---

### Standalone: Record Decision (ad-hoc)

**Command:** `/record-decision`

Use this command for decisions made **outside** the AI workflow — after a team discussion, a design review, or when revisiting a past choice. During normal spec creation, task generation, and development, the AI captures decisions inline automatically.

**What gets created:**
- `specs/<capability>/decisions/NNN-<title>.md`

**Human gate:** Review the ADR for accuracy. If the decision affects the spec, run `/update-spec`.

---

## Quick Reference

| Step | Command | Output | Human Gate | Captures Decisions? |
|------|---------|--------|------------|---------------------|
| Create PRD | `/create-prd` | `specs/<cap>/prd-<cap>.md` + folder structure | Review and refine goals, user stories | No |
| Create spec | `/create-spec` | `specs/<cap>/spec-<cap>.md` + ADRs | Review and refine requirements | Yes — from Q&A |
| Generate tasks | `/generate-tasks` | `specs/<cap>/tasks/tasks-<cap>.md` + ADRs | Approve high-level tasks ("LGTM"), then review sub-tasks | Yes — from breakdown |
| Develop | `/task-development` | Code changes + ADRs | Approve each sub-task ("y") | Yes — inline |
| Update spec | `/update-spec` | Updated `spec-<cap>.md` | Review spec delta before applying | No |
| Record decision | `/record-decision` | `specs/<cap>/decisions/NNN-*.md` | Review ADR accuracy | Standalone fallback |

## Principles

1. **Spec-first:** A well-thought-out spec is written before any code. Requirements and scenarios serve as both documentation and acceptance criteria.

2. **Spec-anchored:** The spec persists after implementation. It continues to serve as the source of truth for evolution and maintenance of the capability.

3. **Spec-as-source:** Over time, the spec is the primary artifact. When requirements change, the spec changes first, then the code follows.

4. **Human-gated:** The AI assists at every step but never advances the process autonomously. Each transition requires explicit human approval.

5. **Semantically organized:** All artifacts for a capability (spec, decisions, tasks) live together in one folder — a semantic bucket that provides complete context for any future work on that capability.

## Migration from Legacy PRDs

Existing PRDs in `.cursor/dev-planning/prd/` are not migrated in bulk. Instead:

- **New work:** Start with `/create-prd` (Step 0), which saves to `specs/<capability>/prd-<capability>.md`.
- **Existing PRDs in progress:** Complete in the current format, then create a capability folder and move the PRD into it.
- **Completed PRDs:** Migrate on demand when the feature needs changes — move the PRD to `specs/<capability>/prd-<capability>.md` and create a spec from it.
