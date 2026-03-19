# Pipe Building Tasks

> **Goal**: 13 MCP tools for pipe, phase, field, and label CRUD — PipeClaw's core builder capabilities
> **Spec**: [../spec-pipe-building.md](../spec-pipe-building.md)
> **Prerequisite**: Schema Introspection (Phase 0) — `introspect_type` enables field type discovery

---

## Relevant Files

- `src/pipefy_mcp/services/pipefy/queries/pipe_config_queries.py` - `gql()` constants for pipe/phase/field/label mutations
- `src/pipefy_mcp/services/pipefy/pipe_config_service.py` - Service with all 13 CRUD methods
- `src/pipefy_mcp/services/pipefy/client.py` - Facade delegation to PipeConfigService
- `src/pipefy_mcp/tools/pipe_config_tools.py` - MCP tool registration for 13 tools
- `src/pipefy_mcp/tools/pipe_config_tool_helpers.py` - Payload builders, error mappers
- `src/pipefy_mcp/tools/registry.py` - ToolRegistry wiring (registers PipeConfigTools)
- `src/pipefy_mcp/services/pipefy/__init__.py` - Public export of PipeConfigService
- `tests/services/pipefy/test_pipe_config_service.py` - Service unit tests
- `tests/tools/test_pipe_config_tools.py` - Tool unit tests
- `tests/tools/test_registry.py` - Asserts PipeConfigTools.register is invoked
- `tests/test_server.py` - Expected tool names include all pipe-building tools
- `README.md` - Documentation for new tools

### Notes

- Unit tests mirror `src/` structure under `tests/`.
- Run `uv run pytest tests/services/pipefy/test_pipe_config_service.py -v` for service tests.
- Run `uv run pytest tests/tools/test_pipe_config_tools.py -v` for tool tests.
- Split into 3 PRs for reviewability (PR A: pipe, PR B: phase, PR C: field+label).

---

## Trigger / Enables / Depends on

**Trigger:** User asks PipeClaw to create or modify a Pipefy workflow.
**Enables:** Phase 3 (Connections) — pipe relations require existing pipes. Phase 4 (Automations) — automations attach to pipes/phases.
**Depends on:** Phase 0 (Schema Introspection) — `introspect_type("CreatePhaseFieldInput")` discovers valid field types.

---

## Acceptance Criteria

- [x] `create_pipe` creates a pipe and returns its ID
- [x] `update_pipe` updates pipe attributes (name, icon, color)
- [x] `delete_pipe` returns a preview by default; deletes only when `confirm=true`
- [x] `clone_pipe` clones a pipe synchronously and returns the new pipe with ID
- [x] `create_phase` creates a phase in a pipe with name, done flag, index
- [x] `update_phase` / `delete_phase` work on existing phases
- [x] `create_phase_field` creates a field with pass-through type validation
- [x] `update_phase_field` / `delete_phase_field` work on existing fields
- [x] `create_label` / `update_label` / `delete_label` manage labels on a pipe
- [x] All `delete_*` tools have `destructiveHint=True` in `ToolAnnotations`
- [ ] `delete_pipe` follows the two-step preview/confirm pattern (like `delete_card`)

---

## Task 1: Define pipe config GraphQL mutations

- [x] **1.1** Create pipe_config_queries.py with pipe mutations
  - **File**: `src/pipefy_mcp/services/pipefy/queries/pipe_config_queries.py` (create new)
  - **What**: Define `gql()` constants: `CREATE_PIPE_MUTATION` (`createPipe` with `input` variable returning `pipe { id name }`), `UPDATE_PIPE_MUTATION` (`updatePipe`), `DELETE_PIPE_MUTATION` (`deletePipe` returning `success`), `CLONE_PIPE_MUTATION` (`clonePipes` with `pipe_template_ids` returning `pipes { id name phases { id name } }`).
  - **Why**: Foundation for all pipe CRUD operations.
  - **Pattern**: Follow `src/pipefy_mcp/services/pipefy/queries/card_queries.py` — `gql()` constants with variables.
  - **Verify**: File imports cleanly; constants are valid `gql()` objects.

- [x] **1.2** Add phase mutations
  - **File**: `src/pipefy_mcp/services/pipefy/queries/pipe_config_queries.py` (modify)
  - **What**: Define `CREATE_PHASE_MUTATION` (`createPhase` with `input` returning `phase { id name done }`), `UPDATE_PHASE_MUTATION` (`updatePhase`), `DELETE_PHASE_MUTATION` (`deletePhase` returning `success`).
  - **Why**: Phase CRUD queries for Task 3.
  - **Pattern**: Same file, same `gql()` pattern.
  - **Verify**: Constants defined and parseable.

- [x] **1.3** Add field mutations
  - **File**: `src/pipefy_mcp/services/pipefy/queries/pipe_config_queries.py` (modify)
  - **What**: Define `CREATE_PHASE_FIELD_MUTATION` (`createPhaseField` with `input` returning `phase_field { id label type }`), `UPDATE_PHASE_FIELD_MUTATION` (`updatePhaseField`), `DELETE_PHASE_FIELD_MUTATION` (`deletePhaseField` returning `success`).
  - **Why**: Field CRUD queries for Task 4.
  - **Pattern**: Same file, same `gql()` pattern.
  - **Verify**: Constants defined and parseable.

- [x] **1.4** Add label mutations
  - **File**: `src/pipefy_mcp/services/pipefy/queries/pipe_config_queries.py` (modify)
  - **What**: Define `CREATE_LABEL_MUTATION` (`createLabel` with `input` returning `label { id name color }`), `UPDATE_LABEL_MUTATION` (`updateLabel`), `DELETE_LABEL_MUTATION` (`deleteLabel` returning `success`).
  - **Why**: Label CRUD queries for Task 4.
  - **Pattern**: Same file, same `gql()` pattern.
  - **Verify**: Constants defined and parseable.

---

## Task 2: Pipe CRUD — service + tools + tests (PR A)

**Enables:** Tasks 3 and 4 (phases and fields need the service + tool pattern established here).

- [x] **2.1** Write tests for PipeConfigService pipe methods
  - **File**: `tests/services/pipefy/test_pipe_config_service.py` (create new)
  - **What**: Test cases for `create_pipe` (success), `update_pipe` (success), `delete_pipe` (returns pipe data for preview), `clone_pipe` (returns cloned pipe with ID). Mock `execute_query` to return expected GraphQL responses.
  - **Why**: TDD red phase — establish expected behavior.
  - **Pattern**: Follow `tests/services/pipefy/test_card_service.py` — mock `execute_query`, assert return shape.
  - **Verify**: `uv run pytest tests/services/pipefy/test_pipe_config_service.py -k "pipe" -v` — tests fail (red).

- [x] **2.2** Implement pipe methods in PipeConfigService
  - **File**: `src/pipefy_mcp/services/pipefy/pipe_config_service.py` (create new)
  - **What**: Create `PipeConfigService(BasePipefyClient)`. Methods: `async create_pipe(name, org_id)`, `async update_pipe(pipe_id, **attrs)`, `async delete_pipe(pipe_id)`, `async clone_pipe(pipe_template_id)`. Each calls `execute_query` with the corresponding mutation and variables.
  - **Why**: Service layer for pipe CRUD — thin delegation to GraphQL.
  - **Pattern**: Follow `src/pipefy_mcp/services/pipefy/card_service.py` — extends `BasePipefyClient`, uses `execute_query`.
  - **Verify**: `uv run pytest tests/services/pipefy/test_pipe_config_service.py -k "pipe" -v` — tests pass (green).

- [x] **2.3** Add pipe methods to PipefyClient facade
  - **File**: `src/pipefy_mcp/services/pipefy/client.py` (modify)
  - **What**: Import `PipeConfigService`. In `__init__`, create `self._pipe_config_service = PipeConfigService(settings=settings, auth=auth)`. Add delegate methods: `create_pipe`, `update_pipe`, `delete_pipe`, `clone_pipe`.
  - **Why**: Facade pattern — tools call `PipefyClient`, not services directly.
  - **Pattern**: Follow existing `_pipe_service` / `_card_service` pattern.
  - **Verify**: Methods exist on `PipefyClient`.

- [x] **2.4** Create pipe_config_tool_helpers.py
  - **File**: `src/pipefy_mcp/tools/pipe_config_tool_helpers.py` (create new)
  - **What**: Define payload builders: `build_pipe_success_payload(data)`, `build_pipe_error_payload(error)`, `build_delete_pipe_preview_payload(pipe_data)`. Format responses as readable text for LLM consumption.
  - **Why**: Keeps tool files focused on MCP registration.
  - **Pattern**: Follow `src/pipefy_mcp/tools/pipe_tool_helpers.py`.
  - **Verify**: File imports cleanly.

- [x] **2.5** Write tests for pipe tools
  - **File**: `tests/tools/test_pipe_config_tools.py` (create new)
  - **What**: Test all 4 pipe tools (mock `PipefyClient`): `create_pipe` success, `update_pipe` success, `delete_pipe` preview (default) and delete (confirm=true), `clone_pipe` success.
  - **Why**: TDD red phase for tool layer.
  - **Pattern**: Follow `tests/tools/test_pipe_tools.py`.
  - **Verify**: Tests fail (red).

- [x] **2.6** Implement pipe tools
  - **File**: `src/pipefy_mcp/tools/pipe_config_tools.py` (create new)
  - **What**: Create `PipeConfigTools` with `@staticmethod register(mcp, client)`. Implement `create_pipe` (params: `name`, `org_id`), `update_pipe` (params: `pipe_id`, optional attrs), `delete_pipe` (params: `pipe_id`, `confirm: bool = False` — follows two-step pattern like `delete_card`), `clone_pipe` (params: `pipe_template_id`). All with `readOnlyHint=False`; `delete_pipe` also has `destructiveHint=True`.
  - **Why**: First 4 of 13 pipe building tools.
  - **Pattern**: Follow `src/pipefy_mcp/tools/pipe_tools.py` — closure-based registration. Follow `delete_card` pattern for `delete_pipe`.
  - **Verify**: All pipe tool tests pass (green). `uv run ruff check src/ && uv run ruff format src/`.

---

## Task 3: Phase CRUD — service + tools + tests (PR B)

**Depends on:** Task 2 (PipeConfigService and PipeConfigTools must exist).

- [x] **3.1** Write tests for phase service methods
  - **File**: `tests/services/pipefy/test_pipe_config_service.py` (modify)
  - **What**: Add test cases: `create_phase` (success with name, pipe_id, done flag), `update_phase` (success), `delete_phase` (success).
  - **Why**: TDD red phase.
  - **Verify**: Tests fail (red).

- [x] **3.2** Implement phase methods in PipeConfigService
  - **File**: `src/pipefy_mcp/services/pipefy/pipe_config_service.py` (modify)
  - **What**: Add methods: `async create_phase(pipe_id, name, done=False, index=None)`, `async update_phase(phase_id, **attrs)`, `async delete_phase(phase_id)`.
  - **Why**: Phase CRUD operations.
  - **Pattern**: Same service, same `execute_query` pattern as pipe methods.
  - **Verify**: Tests pass (green).

- [x] **3.3** Add phase methods to PipefyClient facade
  - **File**: `src/pipefy_mcp/services/pipefy/client.py` (modify)
  - **What**: Add delegate methods: `create_phase`, `update_phase`, `delete_phase`.
  - **Pattern**: Same delegation pattern.
  - **Verify**: Methods exist on facade.

- [x] **3.4** Write tests for phase tools
  - **File**: `tests/tools/test_pipe_config_tools.py` (modify)
  - **What**: Add test cases for `create_phase`, `update_phase`, `delete_phase` tools.
  - **Why**: TDD red phase.
  - **Verify**: Tests fail (red).

- [x] **3.5** Implement phase tools
  - **File**: `src/pipefy_mcp/tools/pipe_config_tools.py` (modify)
  - **What**: Add `create_phase` (params: `pipe_id`, `name`, optional `done`, `index`), `update_phase` (params: `phase_id`, optional attrs), `delete_phase` (params: `phase_id`, `destructiveHint=True`). All `readOnlyHint=False`.
  - **Pattern**: Same closure-based registration within `PipeConfigTools.register`.
  - **Verify**: All phase tool tests pass (green). `uv run ruff check src/`.

---

## Task 4: Field + Label CRUD — service + tools + tests (PR C)

**Depends on:** Task 3 (pattern established in PR A/B).

- [x] **4.1** Write tests for field service methods
  - **File**: `tests/services/pipefy/test_pipe_config_service.py` (modify)
  - **What**: Test cases: `create_phase_field` (success with phase_id, label, type), `update_phase_field` (success), `delete_phase_field` (success).
  - **Verify**: Tests fail (red).

- [x] **4.2** Implement field methods in PipeConfigService
  - **File**: `src/pipefy_mcp/services/pipefy/pipe_config_service.py` (modify)
  - **What**: Add: `async create_phase_field(phase_id, label, type, **attrs)`, `async update_phase_field(field_id, **attrs)`, `async delete_phase_field(field_id)`. Field type is passed through — no local validation.
  - **Verify**: Tests pass (green).

- [x] **4.3** Write tests for label service methods
  - **File**: `tests/services/pipefy/test_pipe_config_service.py` (modify)
  - **What**: Test cases: `create_label` (success with pipe_id, name, color), `update_label` (success), `delete_label` (success).
  - **Verify**: Tests fail (red).

- [x] **4.4** Implement label methods in PipeConfigService
  - **File**: `src/pipefy_mcp/services/pipefy/pipe_config_service.py` (modify)
  - **What**: Add: `async create_label(pipe_id, name, color)`, `async update_label(label_id, **attrs)`, `async delete_label(label_id)`.
  - **Verify**: Tests pass (green).

- [x] **4.5** Add field + label methods to facade
  - **File**: `src/pipefy_mcp/services/pipefy/client.py` (modify)
  - **What**: Add 6 delegate methods: `create_phase_field`, `update_phase_field`, `delete_phase_field`, `create_label`, `update_label`, `delete_label`.
  - **Verify**: Methods exist on facade.

- [x] **4.6** Write tests for field + label tools
  - **File**: `tests/tools/test_pipe_config_tools.py` (modify)
  - **What**: Add test cases for all 6 tools: 3 field tools + 3 label tools.
  - **Verify**: Tests fail (red).

- [x] **4.7** Implement field + label tools
  - **File**: `src/pipefy_mcp/tools/pipe_config_tools.py` (modify)
  - **What**: Add 6 tools within `PipeConfigTools.register`. Field tools: `create_phase_field` (params: `phase_id`, `label`, `type`, optional attrs), `update_phase_field`, `delete_phase_field`. Label tools: `create_label` (params: `pipe_id`, `name`, `color`), `update_label`, `delete_label`. All delete tools have `destructiveHint=True`.
  - **Verify**: All tests pass (green). `uv run ruff check src/ && uv run ruff format src/`.

---

## Task 5: Wire PipeConfigTools + register + README

**Depends on:** Tasks 2-4 (all tools must exist).

- [x] **5.1** Register PipeConfigTools in ToolRegistry
  - **File**: `src/pipefy_mcp/tools/registry.py` (modify)
  - **What**: Import `PipeConfigTools`. Add `PipeConfigTools.register(self.mcp, self.services_container.pipefy_client)` in `register_tools()`.
  - **Why**: Makes all 13 tools available to LLM clients.
  - **Pattern**: Follow existing `PipeTools.register(...)` call.
  - **Verify**: `uv run pytest` — full suite passes.

- [x] **5.2** Export PipeConfigService from package
  - **File**: `src/pipefy_mcp/services/pipefy/__init__.py` (modify)
  - **What**: Add `PipeConfigService` to `__all__` and imports.
  - **Pattern**: Follow existing exports.
  - **Verify**: `from pipefy_mcp.services.pipefy import PipeConfigService` works.

- [x] **5.3** Update README with pipe building tools
  - **File**: `README.md` (modify)
  - **What**: Add "Pipe Building Tools" section documenting all 13 tools grouped by domain (pipe, phase, field, label). Include destructive operation warnings for delete tools.
  - **Pattern**: Follow existing tool documentation format.
  - **Verify**: README renders correctly.

---

## Definition of Done

- [x] All 13 tools callable via MCP Inspector
- [x] `uv run pytest` — full test suite passes
- [x] `uv run pytest --cov=src/pipefy_mcp/services/pipefy --cov-report=term-missing` — ≥95% coverage on PipeConfigService
- [x] `uv run ruff check src/ && uv run ruff format src/` — no lint errors
- [x] `delete_pipe` follows two-step preview/confirm pattern
- [x] All `delete_*` tools have `destructiveHint=True`
- [x] README documents all 13 new tools
