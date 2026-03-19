# Pipe Building Specification

## Purpose

Provide PipeClaw with core builder capabilities. PipeClaw can create and configure complete Pipefy workflows programmatically — pipes, phases, fields, and labels — enabling it to set up an entire process from scratch in a single conversation.

## Goals

1. PipeClaw can create a new pipe and configure it with phases, fields, and labels.
2. PipeClaw can clone existing pipe templates to reuse proven process structures.
3. PipeClaw can update any configuration of an existing pipe, phase, field, or label.
4. PipeClaw can delete pipes, phases, fields, and labels with appropriate safety controls.
5. Each resource is managed atomically (pipe, phases, fields, labels created separately) for better error isolation and LLM debuggability.

## User Stories

- As PipeClaw, I want to **create a pipe with phases, fields, and labels** so I can set up a complete workflow for the user in one go.
- As PipeClaw, I want to **clone an existing pipe template** so I can reuse proven process structures and customize them.
- As PipeClaw, I want to **update pipe, phase, and field configurations** so I can evolve processes as requirements change.
- As PipeClaw, I want to **delete pipes, phases, and fields** (with user confirmation) so I can clean up unused resources.
- As PipeClaw, I want to **manage labels** so I can categorize and classify items within pipes.

## Requirements

### Requirement: Pipe CRUD
The system SHALL allow creation, reading, updating, and deletion of pipes.

#### Scenario: Create a pipe
- GIVEN a valid organization ID and pipe name
- WHEN `create_pipe` is called
- THEN a new pipe is created in the organization
- AND the pipe ID is returned

#### Scenario: Update a pipe
- GIVEN an existing pipe ID
- WHEN `update_pipe` is called with new attributes (name, icon, color, preferences)
- THEN the pipe is updated with the provided values

#### Scenario: Delete a pipe
- GIVEN an existing pipe ID and `confirm=false` (default)
- WHEN `delete_pipe` is called
- THEN a preview of the pipe is returned without deleting

#### Scenario: Delete a pipe with confirmation
- GIVEN an existing pipe ID and `confirm=true`
- WHEN `delete_pipe` is called
- THEN the pipe is permanently deleted

#### Scenario: Clone a pipe
- GIVEN a valid `pipe_template_id`
- WHEN `clone_pipe` is called
- THEN the pipe is cloned synchronously
- AND the new pipe object with its ID is returned

### Requirement: Phase CRUD
The system SHALL allow creation, updating, and deletion of phases within a pipe.

#### Scenario: Create a phase
- GIVEN an existing pipe ID, a phase name, and optional attributes (done flag, index, SLA)
- WHEN `create_phase` is called
- THEN a new phase is created in the pipe at the specified position

#### Scenario: Update a phase
- GIVEN an existing phase ID
- WHEN `update_phase` is called with new attributes (name, description, done flag)
- THEN the phase is updated with the provided values

#### Scenario: Delete a phase
- GIVEN an existing phase ID
- WHEN `delete_phase` is called
- THEN the phase is permanently deleted

### Requirement: Phase field CRUD
The system SHALL allow creation, updating, and deletion of fields within a phase.

#### Scenario: Create a field
- GIVEN an existing phase ID, a field label, and a field type
- WHEN `create_phase_field` is called
- THEN a new field is created in the phase with the specified type
- AND the field type is passed through to the API without local validation

#### Scenario: Discover valid field types
- GIVEN uncertainty about which field types the API supports
- WHEN PipeClaw uses `introspect_type("CreatePhaseFieldInput")` (from Schema Introspection)
- THEN PipeClaw discovers the valid field types without local enum maintenance

#### Scenario: Update a field
- GIVEN an existing field ID
- WHEN `update_phase_field` is called with new attributes (label, options, required, description)
- THEN the field is updated with the provided values

#### Scenario: Delete a field
- GIVEN an existing field ID
- WHEN `delete_phase_field` is called
- THEN the field is permanently deleted

### Requirement: Label CRUD
The system SHALL allow creation, updating, and deletion of labels within a pipe.

#### Scenario: Create a label
- GIVEN an existing pipe ID, a label name, and a color
- WHEN `create_label` is called
- THEN a new label is created in the pipe

#### Scenario: Update a label
- GIVEN an existing label ID
- WHEN `update_label` is called with new attributes (name, color)
- THEN the label is updated

#### Scenario: Delete a label
- GIVEN an existing label ID
- WHEN `delete_label` is called
- THEN the label is permanently deleted

### Requirement: Destructive operation safety
The system SHALL enforce safety controls on all destructive operations.

#### Scenario: High-risk deletion (pipe)
- GIVEN a `delete_pipe` call
- WHEN `confirm` is not explicitly set to `true`
- THEN the tool returns a preview of the pipe details without deleting
- AND the response instructs the LLM to confirm with the user

#### Scenario: Standard deletion (phase, field, label)
- GIVEN a delete call for phase, field, or label
- WHEN the tool is called
- THEN the deletion is executed directly (no preview step)
- AND the tool's docstring instructs the LLM to always confirm with the user first

#### Scenario: Tool annotations for destructive tools
- GIVEN any `delete_*` tool in this capability
- WHEN it is registered with the MCP server
- THEN it has `destructiveHint=True` in its `ToolAnnotations`

### Requirement: Tool annotations
The system SHALL set appropriate MCP tool annotations for all tools.

#### Scenario: Read tools
- GIVEN `get_pipe` (already exists)
- THEN it has `readOnlyHint=True`

#### Scenario: Write tools
- GIVEN `create_*`, `update_*`, and `clone_*` tools
- WHEN they are registered
- THEN they have `readOnlyHint=False`

## Non-Goals

- **No inline pipe creation.** Phases, fields, and labels are created separately (atomic approach) — not bundled into `create_pipe`.
- **No field type validation.** The API validates field types — PipeClaw can use `introspect_type` from Schema Introspection to discover valid types. No local enum to maintain.
- **No pipe templates listing.** PipeClaw can use existing `search_schema` + `clone_pipe` with known template IDs.

## Technical Context

### Architecture

Follows existing patterns:

| Layer | File | Responsibility |
|-------|------|---------------|
| Queries | `services/pipefy/queries/pipe_config_queries.py` | `gql()` constants for pipe, phase, field, label mutations |
| Service | `services/pipefy/pipe_config_service.py` | Methods for all 13 tools (pipe CRUD, phase CRUD, field CRUD, label CRUD) |
| Facade | `services/pipefy/client.py` | Delegate to `PipeConfigService` |
| Tools | `tools/pipe_config_tools.py` | Register 13 tools via `@mcp.tool()` |
| Helpers | `tools/pipe_config_tool_helpers.py` | Payload builders, error mappers |

### Service design

- `PipeConfigService` extends `BasePipefyClient` (receives `PipefySettings` + shared `auth`).
- Each method maps directly to a GraphQL mutation (thin delegation, no business logic).
- `delete_pipe` supports a two-step flow: preview (default) then confirm — same pattern as existing `delete_card`.
- `clone_pipe` uses `clonePipes` mutation which returns `pipes: [Pipe!]` synchronously.

### Wiring

- `PipefyClient.__init__` creates `PipeConfigService` alongside existing services.
- `ToolRegistry.register_tools()` calls `PipeConfigTools.register(mcp, client)`.

### Existing read tools

`get_pipe` and `get_start_form_fields` already exist in `PipeService` / `PipeTools`. The new tools handle write operations only (create, update, delete, clone).

### PR strategy

Split into 2-3 PRs for reviewability:
- **PR A:** Pipe CRUD (`create_pipe`, `update_pipe`, `delete_pipe`, `clone_pipe`) + tests
- **PR B:** Phase CRUD (`create_phase`, `update_phase`, `delete_phase`) + tests
- **PR C:** Field + Label CRUD (`create_phase_field`, `update_phase_field`, `delete_phase_field`, `create_label`, `update_label`, `delete_label`) + tests

Each PR target: ≤10 files, ≤300 lines.

## Open Questions

None — design decisions were resolved in the PRD (see `specs/pipeclaw-full-toolset/prd-pipeclaw-full-toolset.md`, Decisions Log #3 and #5).
