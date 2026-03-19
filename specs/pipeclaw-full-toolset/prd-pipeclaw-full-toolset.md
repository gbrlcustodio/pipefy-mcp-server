# PRD: PipeClaw Full Toolset — Expanding the Pipefy MCP Server

## 1. Introduction / Overview

The Pipefy MCP server currently exposes **22 tools** covering cards, comments, pipes (read-only), and AI Agents/Automations. **PipeClaw** — an OpenClaw-based agent that designs, builds, and manages business processes inside Pipefy — needs the ability to **create, configure, and connect entire workflows programmatically**.

This PRD defines the full set of tools needed so PipeClaw has every capability the Pipefy GraphQL API offers, enabling it to solve any process problem a user presents: from creating a pipe with phases and fields, to linking pipes together, setting up automations, managing database tables, and orchestrating cross-pipe workflows.

**Guiding principle:** Give PipeClaw ALL possible tools the API allows, so it can solve any user problem within Pipefy. When a specific tool doesn't exist or fails, PipeClaw can fall back to schema introspection and raw GraphQL execution to self-heal.

---

## 2. Goals

1. **Complete builder capabilities**: PipeClaw can create a full process from scratch (pipe → phases → fields → automations → connections) in a single conversation.
2. **Database access**: PipeClaw can read and write to Pipefy Database Tables as reference data stores.
3. **Cross-pipe orchestration**: PipeClaw can create pipe relations and card relations to build connected workflows.
4. **Automation management**: PipeClaw can set up both traditional automations and AI automations/agents.
5. **Full lifecycle**: Every resource PipeClaw creates, it can also read, update, and delete.
6. **Self-healing fallback**: PipeClaw can introspect the GraphQL schema and execute raw queries when a dedicated tool doesn't exist or fails due to API changes.
7. **Small, reviewable PRs**: Each phase delivers a self-contained set of tools (≤10 files, ≤300 lines changed per PR).

---

## 3. User Stories

### Process Builder
- As PipeClaw, I want to **create a pipe with phases, fields, and labels** so I can set up a complete workflow for the user in one go.
- As PipeClaw, I want to **clone an existing pipe template** so I can reuse proven process structures and customize them.
- As PipeClaw, I want to **create field conditions** so fields appear/hide based on other field values.

### Database Manager
- As PipeClaw, I want to **read database table records** so I can look up reference data (e.g., customer list, product catalog).
- As PipeClaw, I want to **create and update table records** so I can sync data from external sources (e.g., a lead from HubSpot MCP).
- As PipeClaw, I want to **create new database tables** so I can set up reference data stores for new processes.

### Cross-Pipe Orchestrator
- As PipeClaw, I want to **create pipe relations** so I can link a "Purchase Order" pipe to a "Receiving" pipe.
- As PipeClaw, I want to **create card relations** so I can connect a specific order card to its delivery card.

### Automation Manager
- As PipeClaw, I want to **create traditional automations** (e.g., "when card moves to Done, send email") so I can automate repetitive steps.
- As PipeClaw, I want to **list and read existing AI Agents** so I know what's already configured before creating new ones.

### Process Maintainer
- As PipeClaw, I want to **update pipe, phase, and field configurations** so I can evolve processes as requirements change.
- As PipeClaw, I want to **delete pipes, phases, and fields** (with user confirmation) so I can clean up unused resources.
- As PipeClaw, I want to **manage labels** so I can categorize and classify items within pipes.

### Self-Healing Agent
- As PipeClaw, when a tool **fails due to API changes**, I want to **introspect the schema** to discover the correct input shape and retry with a raw GraphQL call.
- As PipeClaw, when a user asks me to do something for which **no dedicated tool exists**, I want to **search the schema** for relevant mutations, inspect their arguments, and **execute the operation directly** via raw GraphQL.
- As PipeClaw, I want to **discover new API capabilities** without waiting for a code release, so I can always offer the user the latest Pipefy features.

---

## 4. Functional Requirements — New Tools

### Phase 0: Schema Introspection & Raw Execution (Self-Healing Fallback)

PipeClaw's safety net: when dedicated tools don't exist or fail, these tools let PipeClaw discover and call ANY GraphQL operation directly.

| # | Tool | Description |
|---|------|-------------|
| 0.1 | `introspect_type` | Inspect a GraphQL type's fields, input fields, or enum values. Use to understand the shape of an API request/response before building it. |
| 0.2 | `introspect_mutation` | Get a mutation's name, description, and argument types. Use to discover how to call a mutation that doesn't have a dedicated tool. |
| 0.3 | `search_schema` | Search the GraphQL schema by keyword (case-insensitive). Returns matching type names, kinds, and descriptions. Use to find relevant operations for a task. |
| 0.4 | `execute_graphql` | Execute an arbitrary GraphQL query or mutation with variables. **This is the ultimate fallback** — if no dedicated tool exists, PipeClaw can introspect the schema, build the query, and execute it directly. |

**Why Phase 0:** These tools are foundational — they make PipeClaw resilient from day one. Even before we build Phase 1-6 tools, PipeClaw can use introspection + `execute_graphql` to perform any API operation. As we add dedicated tools, they become the preferred path (better validation, clearer docstrings, typed responses), but the raw fallback always remains available.

**Design notes:**
- `introspect_type`, `introspect_mutation`, and `search_schema` are **read-only** (`readOnlyHint=True`).
- `execute_graphql` is **not read-only** (it can run mutations). Its docstring should instruct the LLM: *"Prefer dedicated tools when available. Use this as a fallback when no specific tool exists for the operation. Always introspect the mutation's input shape before executing."*
- `execute_graphql` should accept `query` (string) and `variables` (dict), and return the raw JSON response. It should detect and surface GraphQL errors clearly.
- `execute_graphql` targets the **standard GraphQL endpoint only**. The `internal_api` endpoint is already fully covered by dedicated AI Automation tools. If new internal API features emerge in the future, a separate `execute_internal_graphql` tool can be added then.
- **No guardrails / blocklist** on `execute_graphql`. The MCP is a toolbox — security responsibility belongs to the agent's operational rules (AGENTS.md), not the MCP. The service account already scopes access to the org.

**PR strategy:** Single PR (PR 0) — 4 tools, self-contained, no dependencies on other phases.

### Phase 1: Pipe Building (Core Builder)

The foundation: PipeClaw can create and configure complete workflows.

| # | Tool | API Operation | Description |
|---|------|--------------|-------------|
| 1.1 | `create_pipe` | `createPipe` | Create a new pipe with name and org_id. Phases, fields, and labels are created separately via dedicated tools (atomic approach for better error isolation and LLM debuggability). |
| 1.2 | `update_pipe` | `updatePipe` | Update pipe name, icon, color, preferences |
| 1.3 | `delete_pipe` | `deletePipe` | Delete a pipe (**destructive — requires user confirmation**) |
| 1.4 | `clone_pipe` | `clonePipes` | Clone a pipe from a template by pipe_template_id. Returns the new pipe(s) synchronously with full Pipe objects including IDs. |
| 1.5 | `create_phase` | `createPhase` | Create a phase in a pipe (name, done flag, index, SLA) |
| 1.6 | `update_phase` | `updatePhase` | Update phase name, description, done flag |
| 1.7 | `delete_phase` | `deletePhase` | Delete a phase (**destructive**) |
| 1.8 | `create_phase_field` | `createPhaseField` | Create a field in a phase (label, type, options, required, etc.). Field type is passed through to the API without local validation — PipeClaw can use `introspect_type("CreatePhaseFieldInput")` to discover valid types. |
| 1.9 | `update_phase_field` | `updatePhaseField` | Update field label, options, required, description |
| 1.10 | `delete_phase_field` | `deletePhaseField` | Delete a field (**destructive**) |
| 1.11 | `create_label` | `createLabel` | Create a label in a pipe |
| 1.12 | `update_label` | `updateLabel` | Update a label's name or color |
| 1.13 | `delete_label` | `deleteLabel` | Delete a label (**destructive**) |

**PR strategy:** Split into 2-3 PRs:
- PR A: Pipe CRUD (1.1-1.4) + tests
- PR B: Phase CRUD (1.5-1.7) + tests
- PR C: Field + Label CRUD (1.8-1.13) + tests

### Phase 2: Database Tables

PipeClaw can read and manage structured reference data.

| # | Tool | API Operation | Description |
|---|------|--------------|-------------|
| 2.1 | `get_table` | `table` query | Get a database table by ID (fields, settings) |
| 2.2 | `get_tables` | `tables` query | List database tables by IDs |
| 2.3 | `get_table_records` | `table_records` query | List records from a table with cursor-based pagination. Configurable page size via `first` param (default 50, max 200). Returns `hasNextPage` + `endCursor` for continuation. |
| 2.4 | `get_table_record` | `table_record` query | Get a single record by ID with field values |
| 2.5 | `find_records` | `findRecords` query | Search records by field values |
| 2.6 | `create_table` | `createTable` | Create a new database table |
| 2.7 | `update_table` | `updateTable` | Update table name, description |
| 2.8 | `delete_table` | `deleteTable` | Delete a table (**destructive**) |
| 2.9 | `create_table_record` | `createTableRecord` | Create a record in a table |
| 2.10 | `update_table_record` | `updateTableRecord` | Update a table record |
| 2.11 | `delete_table_record` | `deleteTableRecord` | Delete a record (**destructive**) |
| 2.12 | `set_table_record_field_value` | `setTableRecordFieldValue` | Update a single field on a record |
| 2.13 | `create_table_field` | `createTableField` | Create a field in a table |
| 2.14 | `update_table_field` | `updateTableField` | Update a table field |
| 2.15 | `delete_table_field` | `deleteTableField` | Delete a table field (**destructive**) |

**PR strategy:** Split into 2-3 PRs:
- PR D: Table read (2.1-2.5) + tests
- PR E: Table CRUD (2.6-2.8) + record CRUD (2.9-2.12) + tests
- PR F: Table field CRUD (2.13-2.15) + tests

### Phase 3: Connections & Relations

PipeClaw can link pipes and connect cards across workflows.

| # | Tool | API Operation | Description |
|---|------|--------------|-------------|
| 3.1 | `create_pipe_relation` | `createPipeRelation` | Create a parent-child relation between two pipes |
| 3.2 | `update_pipe_relation` | `updatePipeRelation` | Update relation config (auto-fill, constraints) |
| 3.3 | `delete_pipe_relation` | `deletePipeRelation` | Delete a pipe relation (**destructive**) |
| 3.4 | `get_pipe_relations` | `pipe_relations` query | List relations for a pipe |
| 3.5 | `get_table_relations` | `table_relations` query | List relations for a table |
| 3.6 | `create_card_relation` | `createCardRelation` | Connect a child card to a parent card via a relation |

**PR strategy:** Single PR (PR G) — 6 tools, self-contained.

### Phase 4: Automations (Traditional)

PipeClaw can create trigger-based automation rules.

| # | Tool | API Operation | Description |
|---|------|--------------|-------------|
| 4.1 | `get_automation` | `automation` query | Get an automation by ID |
| 4.2 | `get_automations` | `automations` query | List automations by org/pipe with filters |
| 4.3 | `get_automation_actions` | `automationActions` query | List available actions for a pipe |
| 4.4 | `get_automation_events` | `automationEvents` query | List available events for a pipe |
| 4.5 | `create_automation` | `createAutomation` | Create a traditional automation rule |
| 4.6 | `update_automation` | `updateAutomation` | Update an automation rule |
| 4.7 | `delete_automation` | `deleteAutomation` | Delete an automation (**destructive**) |

**PR strategy:** Split into 2 PRs:
- PR H: Read tools (4.1-4.4) + tests
- PR I: Write tools (4.5-4.7) + tests

### Phase 5: AI Agent Read & Field Conditions

PipeClaw can inspect existing AI Agents and manage conditional field logic.

| # | Tool | API Operation | Description |
|---|------|--------------|-------------|
| 5.1 | `get_ai_agent` | `aiAgent` query | Get an AI Agent by UUID |
| 5.2 | `get_ai_agents` | `aiAgents` query | List AI Agents for a pipe |
| 5.3 | `delete_ai_agent` | `deleteAiAgent` | Delete an AI Agent (**destructive**) |
| 5.4 | `create_field_condition` | `createFieldCondition` | Create a conditional field rule |
| 5.5 | `update_field_condition` | `updateFieldCondition` | Update a conditional field rule |
| 5.6 | `delete_field_condition` | `deleteFieldCondition` | Delete a conditional field rule (**destructive**) |

**PR strategy:** Single PR (PR J) — 6 tools.

### Phase 6: Members, Emails & Advanced

| # | Tool | API Operation | Description |
|---|------|--------------|-------------|
| 6.1 | `invite_members` | `inviteMembers` | Invite users to a pipe/org |
| 6.2 | `remove_member_from_pipe` | `removeMembersFromPipe` | Remove members from a pipe |
| 6.3 | `set_role` | `setRole` | Set a member's role on a pipe |
| 6.4 | `send_inbox_email` | `sendInboxEmail` | Send an email from a card's inbox |
| 6.5 | `create_webhook` | `createWebhook` | Register a webhook for pipe events |
| 6.6 | `delete_webhook` | `deleteWebhook` | Delete a webhook |

**PR strategy:** Split by domain:
- PR K: Members (6.1-6.3) + tests
- PR L: Email + Webhooks (6.4-6.6) + tests

---

## 5. Non-Goals (Out of Scope)

1. **Organization management**: `createOrganization`, `deleteOrganization`, `updateOrganization` — PipeClaw operates within a single org via service account.
2. **Service account management**: `createServiceAccount`, `deleteServiceAccount` — security-sensitive, managed externally.
3. **LLM provider management**: `createLlmProvider`, `updateLlmProvider`, `setActiveLlmProvider` — BYOLLM config is an admin-only concern.
4. **Report export**: `exportPipeReport`, `exportOrganizationReport` — reporting is a view layer concern, not orchestration.
5. **AI Agent logs/usage**: `aiAgentLogsByRepo`, `agentsUsageDetails` — agents already log to Pipefy core tables; observability is a separate product concern.
6. **Records importer / Cards importer**: Bulk import operations are out of scope (handled by Pipefy UI).
7. **WhatsApp / Channel configuration**: Communication channels are managed externally.
8. **SMTP configuration**: Email infrastructure is an admin concern.
9. **Pipe templates listing**: `pipe_templates` — useful but low priority; PipeClaw can use `search_pipes` + `clone_pipe` with known template IDs.
10. **Tags / Tag categories**: Tag management is niche; can be added later if needed.

---

## 6. Design Considerations

### Destructive Operations Policy

All destructive tools (`delete_*`) must:
- Include `readOnlyHint=False` in `ToolAnnotations`
- Have docstrings that explicitly instruct the LLM: *"This action is irreversible. Always confirm with the user before executing."*
- Follow the same confirmation pattern as the existing `delete_card` tool (preview → confirm → execute)

For **high-risk** operations (`delete_pipe`, `delete_table`), consider requiring a `confirm=true` parameter (same pattern as `delete_card`).

### Tool Naming Convention

Follow existing patterns:
- Read: `get_*` (single item), `get_*s` (list), `find_*` (search), `search_*` (fuzzy)
- Write: `create_*`, `update_*`, `delete_*`
- Special: `clone_*`, `move_*`, `toggle_*`, `set_*`

### Docstrings for LLM Routing

Tool docstrings are consumed by LLMs for routing. Write them as clear, concise action descriptions explaining WHEN to use the tool and HOW it relates to other tools. Example:

> "Create a phase in a pipe. Phases represent stages of the workflow (e.g., 'Submitted', 'In Review', 'Done'). Use `get_pipe` to see existing phases before creating new ones. Set `done=true` for final phases."

---

## 7. Technical Considerations

### Architecture

All new tools follow the existing architecture:
- **Tools** (`src/pipefy_mcp/tools/`) — thin wrappers, validate input, delegate to service
- **Services** (`src/pipefy_mcp/services/pipefy/`) — domain logic, GraphQL execution
- **Queries** (`src/pipefy_mcp/services/pipefy/queries/`) — `gql()` constants
- **Models** (`src/pipefy_mcp/models/`) — Pydantic input validation

### New Services Needed

| Service | Responsibility | Tools it serves |
|---------|---------------|-----------------|
| `SchemaIntrospectionService` | Schema queries, raw GraphQL execution | Phase 0 (0.1-0.4) |
| `PipeConfigService` | Pipe, phase, field, label CRUD | Phase 1 (1.1-1.13) |
| `TableService` | Database table + record + field CRUD | Phase 2 (2.1-2.15) |
| `RelationService` | Pipe and card relation management | Phase 3 (3.1-3.6) |
| `AutomationService` | Traditional automation CRUD + queries | Phase 4 (4.1-4.7) |

Existing services that gain new tools:
- `AiAgentService` — gains read + delete (Phase 5: 5.1-5.3)
- `PipefyClient` (facade) — delegates to new services

### SchemaIntrospectionService Design

This service wraps GraphQL introspection queries and raw execution. Key considerations:
- Uses `BasePipefyClient` like other services for standard GraphQL endpoint
- `execute_graphql` accepts a raw query string (not `gql()` parsed) — use `gql(query_string)` internally to validate syntax before sending
- Returns raw JSON dict responses (no TypedDict — the shape is dynamic by nature)
- Error handling: catch `gql.TransportQueryError` and surface GraphQL errors clearly in the response

### Automation CRUD Endpoint

**Confirmed:** `createAutomation` exists in the standard GraphQL schema and supports ALL action types (move card, send email, HTTP request, SLA rules, task assignment, etc.). Traditional automations use the standard GraphQL endpoint via `BasePipefyClient`. Only the `generate_with_ai` action requires the `internal_api` endpoint (already handled by `AiAutomationService`).

### Dependencies

No new Python packages needed. All tools use existing `gql`, `httpx`, `pydantic` stack.

---

## 8. Success Metrics

| Metric | Target |
|--------|--------|
| **Tool count** | From 22 → ~75 tools covering all Pipefy API domains + introspection fallback |
| **Test coverage** | ≥ 95% on all new services |
| **PR size** | ≤ 10 files, ≤ 300 lines per PR |
| **CI green** | All PRs pass lint + test before merge |
| **Self-healing** | PipeClaw can discover and execute any GraphQL operation via introspection + `execute_graphql`, even if no dedicated tool exists |
| **PipeClaw end-to-end** | PipeClaw can create a pipe from scratch, add phases/fields/labels, create database table, connect pipes, set up automation, and configure AI agent — all in one conversation |

---

## 9. Delivery Roadmap

| Phase | PRs | Tools | Priority |
|-------|-----|-------|----------|
| **Phase 0: Introspection & Raw Execution** | PR 0 | 4 tools | P0 — Self-healing fallback |
| **Phase 1: Pipe Building** | A, B, C | 13 tools | P0 — Core builder |
| **Phase 2: Database Tables** | D, E, F | 15 tools | P0 — Reference data |
| **Phase 3: Connections** | G | 6 tools | P1 — Cross-pipe |
| **Phase 4: Automations** | H, I | 7 tools | P1 — Rules engine |
| **Phase 5: AI Read + Conditions** | J | 6 tools | P2 — Enhancement |
| **Phase 6: Members + Advanced** | K, L | 6 tools | P3 — Governance |

**Total: ~57 new tools across ~13 PRs**

Combined with the existing 22 tools → **~79 tools** giving PipeClaw full API coverage + self-healing introspection.

**Phase 0 goes first** because it immediately makes PipeClaw capable of any API operation — even before we build the dedicated tools in Phases 1-6. Each subsequent phase then adds a better developer experience (validation, typed responses, clear docstrings) on top of the raw fallback.

---

## 10. Decisions Log

All open questions have been resolved. Decisions are recorded here for future reference.

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | `clonePipes` response shape | **Synchronous** — returns `pipes: [Pipe!]` with IDs immediately | Verified via introspection of `ClonePipesPayload` |
| 2 | Automation CRUD endpoint | **Standard GraphQL** for all non-AI automations; `internal_api` only for `generate_with_ai` | Verified: `createAutomation` exists in standard schema with all action types |
| 3 | `createPipe` inline vs. atomic | **Atomic** — pipe, phases, fields, labels created separately | Better error isolation; consistent with existing patterns; simpler for LLM debugging |
| 4 | Table record pagination | **Configurable** — `first` param, default 50, max 200; returns `hasNextPage` + `endCursor` | Balances performance and flexibility without timeout risk |
| 5 | Field types validation | **Pass-through** — API validates; no local enum | Zero maintenance; PipeClaw can use `introspect_type` to discover valid types |
| 6 | `execute_graphql` guardrails | **No guardrails** — MCP is a toolbox; agent's AGENTS.md owns security | Service account already scopes access; blocklists create false security and limit fallback |
| 7 | Internal API fallback | **Standard endpoint only** — `internal_api` covered by dedicated AI Automation tools | 99% of operations use standard endpoint; can add `execute_internal_graphql` later if needed |
