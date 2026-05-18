# ADR 0001 — Pipeclaw Skill Mapping

**Date:** 2026-05-14
**Status:** Accepted
**Author:** Adrianno Esnarriaga

---

## Context

The `pipefy-labs` monorepo ships a `skills/` catalog of Anthropic Skills-format playbooks. The source material for this catalog is the **pipeclaw** library (`/Users/adrianno.esnarriaga/Coding/pipeless/product/openclaw/`) — a battle-tested set of agent skills used in production through OpenClaw (a WebSocket-based autonomous Pipefy agent).

Before populating `skills/`, every pipeclaw file was classified as (a) direct port, (b) adapt, or (c) defer/not portable, per PRD FR-7.

---

## Source material

**Location:** `/Users/adrianno.esnarriaga/Coding/pipeless/product/openclaw/`

**12 skill files** under `skills/<name>/SKILL.md`:
`ai-agents`, `api-troubleshoot`, `automations`, `database-tables`, `introspection`, `members-email-webhooks`, `observability`, `pipes-and-cards`, `process-design`, `process-intelligence`, `relations`, `reports`

**8 top-level files** (persona/identity/context):
`AGENTS.md`, `BOOT.md`, `BOOTSTRAP.md`, `HEARTBEAT.md`, `IDENTITY.md`, `SOUL.md`, `TOOLS.md`, `USER.md`

---

## Classification table

### Skill files (primary import targets)

| Source path | Destination | Classification | Notes |
|-------------|-------------|----------------|-------|
| `skills/ai-agents/SKILL.md` | `skills/ai-agents/pipefy-ai-agents/SKILL.md` | **(a) Direct port** | Rename references from `mcporter call pipefy` to include both MCP and `pipefy agent` CLI variants. |
| `skills/api-troubleshoot/SKILL.md` | `skills/api-troubleshoot/pipefy-api-fallback/SKILL.md` | **(a) Direct port** | MCP and CLI variants both reference `execute_graphql` / `pipefy graphql exec`. |
| `skills/automations/SKILL.md` | `skills/automations/pipefy-automations/SKILL.md` | **(a) Direct port** | Add CLI examples (`pipefy automation list/create`). |
| `skills/database-tables/SKILL.md` | `skills/database-tables/pipefy-database-tables/SKILL.md` | **(a) Direct port** | CLI parity: `pipefy table`, `pipefy record`. |
| `skills/introspection/SKILL.md` | `skills/introspection/pipefy-introspection/SKILL.md` | **(a) Direct port** | CLI: `pipefy introspect`, `pipefy graphql exec`. |
| `skills/members-email-webhooks/SKILL.md` | `skills/members-email-webhooks/pipefy-members-email-webhooks/SKILL.md` | **(a) Direct port** | CLI: `pipefy member`, `pipefy webhook`. |
| `skills/observability/SKILL.md` | `skills/observability/pipefy-observability/SKILL.md` | **(a) Direct port** | CLI: `pipefy usage agents/automations`. |
| `skills/pipes-and-cards/SKILL.md` | `skills/pipes-and-cards/pipefy-pipes-and-cards/SKILL.md` | **(a) Direct port** | CLI: `pipefy card`, `pipefy pipe`, `pipefy phase`, `pipefy field`. |
| `skills/process-design/SKILL.md` | `skills/process-design/pipefy-process-design/SKILL.md` | **(b) Adapt** | Remove PipeClaw persona references ("You are PipeClaw"). Reframe as a general consulting skill. |
| `skills/process-intelligence/SKILL.md` | `skills/process-intelligence/pipefy-process-intelligence/SKILL.md` | **(b) Adapt** | Same — strip PipeClaw identity framing. Keep the "investigate, diagnose, improve" methodology. |
| `skills/relations/SKILL.md` | `skills/relations/pipefy-relations/SKILL.md` | **(a) Direct port** | CLI: `pipefy relation pipe`, `pipefy relation card`. |
| `skills/reports/SKILL.md` | `skills/reports/pipefy-reports/SKILL.md` | **(a) Direct port** | CLI: `pipefy report-pipe`, `pipefy report-org` (v0.5). |

### Top-level files

| Source file | Classification | Notes |
|-------------|----------------|-------|
| `AGENTS.md` | **(b) Adapt → `skills/AGENTS.md`** | The operational/behavioral rules for PipeClaw are adapted into a skill-authoring guide for `pipefy-labs` contributors. All persona-specific sections (SOUL, USER, memory system, mcporter syntax) are dropped. Tool-call and execution heuristics are kept as authoring guidance. |
| `TOOLS.md` | **(b) Adapt → referenced in skills body** | mcporter invocation syntax documented inside individual skills as the MCP variant (alongside CLI equivalents). No top-level copy needed. |
| `IDENTITY.md` | **(c) Defer** | PipeClaw-specific persona definition. Not portable to a general skill catalog. |
| `SOUL.md` | **(c) Defer** | Same — persona/personality file. |
| `HEARTBEAT.md` | **(c) Defer** | Session health/liveness mechanism specific to OpenClaw WebSocket. |
| `BOOTSTRAP.md` | **(c) Defer** | OpenClaw startup sequence. Not applicable. |
| `BOOT.md` | **(c) Defer** | Same. |
| `USER.md` | **(c) Defer** | Per-user/org memory file for OpenClaw. Not applicable to a general catalog. |

---

## Decision

**Port all 12 skill files** (10 as direct ports, 2 as adapt) into the `skills/` catalog under the same domain structure. Defer all 8 top-level persona/identity files with the rationale above.

**Starter pack (embedded in `pipefy-cli`):** the 8 highest-impact skills for daily Pipefy automation work:
1. `pipes-and-cards` — covers the highest-traffic MCP surface (37 tools)
2. `database-tables` — second-highest (17 tools)
3. `automations` — common ops workflow
4. `ai-agents` — fast-growing; early-adopter demand
5. `introspection` — power user / self-healing fallback
6. `relations` — cross-pipe orchestration
7. `process-design` — consulting/architecture use case
8. `observability` — debugging and usage monitoring

---

## Consequences

- `skills/` launches with ≥ 12 skills (meets G1 from PRD).
- Starter pack of 8 skills embedded in CLI (meets G2).
- No persona-specific files pollute the general catalog.
- Future contributors can add skills without reading pipeclaw source.
- CI (`skills-lint.yml`) validates all ports stay current with tool renames.

---

## Related

- After this mapping is accepted, populate `skills/` from the classification table, then keep the CLI starter pack in sync via `scripts/sync_starter_pack.py` and CI (`skills-lint.yml`).
