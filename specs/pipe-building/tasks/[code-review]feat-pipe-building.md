# Code Review: feat/pipe-building

## 1. Executive Summary

| Category         | Status | Summary |
| :--------------- | :----- | :------ |
| **Architecture** | ✅     | Clean layering: queries → service → facade → tools → helpers. Follows established patterns. |
| **Security**     | ✅     | No secrets, no string interpolation in GraphQL, no sensitive data leaks. |
| **Tests**        | ✅     | Sad-path GraphQL tests per tool, validation edge cases, service error propagation; `extract_payload` handles structured mutation `result`. |
| **Code Quality** | ✅     | Shared `handle_pipe_config_tool_graphql_error`, `extra_input` reserved keys; structured success payloads; consistent optional `debug` on builder tools. |

> **General Feedback:** Solid feature addition — 13 new MCP tools with proper service extraction, query constants, TypedDict payloads, facade wiring, and two-step delete confirmation. The main areas for improvement are (a) extracting the repeated error-handling boilerplate into a shared helper, (b) adding sad-path tests for GraphQL failures across tools, and (c) guarding against `extra_input` key collisions with primary arguments.

## 2. Required Fixes (Must Address Before Merge)

**Status:** Addressed in branch (reserved-key stripping, tests, shared error helper, structured `result`, fixture fix).

### 2.1 `extra_input` can silently shadow primary arguments

- **Location:** `src/pipefy_mcp/tools/pipe_config_tools.py:484-491` (create_phase_field), `:539` (update_phase_field), `:682` (update_label)
- **Problem:** `extra_input` is unpacked as `**merged` and passed alongside positional args. If the caller sends `extra_input={"phase_id": 99}`, Python raises `TypeError: got multiple values for argument 'phase_id'`, which is caught by the generic `except Exception` and returned as a vague "Create phase field failed." error — no indication that the problem was a conflicting key.
- **Rationale:** LLMs or users could accidentally include a primary key in `extra_input`, leading to confusing, hard-to-debug error messages. Explicit key-stripping or validation makes the contract unambiguous.
- **Fix:**

```python
# In create_phase_field, before calling the service:
RESERVED_KEYS = {"phase_id", "label", "type"}
merged: dict[str, Any] = {
    k: v for k, v in (extra_input or {}).items()
    if k not in RESERVED_KEYS
}
```

Apply the same pattern to `update_phase_field` (reserved: `{"id"}`) and `update_label` (reserved: `{"id"}`).

### 2.2 Missing sad-path tests for GraphQL errors on non-delete tools

- **Location:** `tests/tools/test_pipe_config_tools.py`
- **Problem:** Only `delete_pipe` has tests for `TransportQueryError` (not-found mapping). The remaining 12 tools (`create_pipe`, `update_pipe`, `clone_pipe`, `create_phase`, `update_phase`, `delete_phase`, `create_phase_field`, `update_phase_field`, `delete_phase_field`, `create_label`, `update_label`, `delete_label`) have zero API-error tests.
- **Rationale:** Without sad-path tests, regressions in error handling go undetected. A single generic test per tool verifying that `TransportQueryError` returns `success: False` with a message would significantly improve confidence.
- **Fix:** Add at least one error-path test per tool. Example for `create_pipe`:

```python
@pytest.mark.anyio
@pytest.mark.parametrize("pipe_config_session", [None], indirect=True)
async def test_create_pipe_graphql_error_returns_failure(
    pipe_config_session, mock_pipe_config_client, extract_payload
):
    mock_pipe_config_client.create_pipe.side_effect = TransportQueryError(
        "GraphQL Error",
        errors=[{"message": "Organization not found"}],
    )
    async with pipe_config_session as session:
        result = await session.call_tool(
            "create_pipe",
            {"name": "Test", "organization_id": 999},
        )
    payload = extract_payload(result)
    assert payload["success"] is False
    assert "Organization not found" in payload["error"]
```

## 3. Deep Dive Findings

### A. Logic & Concurrency

- [x] **Logic**: `update_phase` auto-resolves current name via `get_phase_fields` when `name` is omitted — correct two-call pattern, avoids losing the name on partial update.
- [x] **Logic**: `delete_pipe` two-step flow (preview → confirm) mirrors the established `delete_card` pattern.
- [x] **Wasted computation**: `handle_pipe_config_tool_graphql_error` skips code/correlation extraction when `debug=False`; optional `debug` added to all pipe-config mutation tools for consistency.

### B. Security & Secrets

- [x] No hardcoded secrets.
- [x] All GraphQL queries use variable substitution.
- [x] Error messages don't leak internal details (correlation IDs hidden behind `debug` flag).

### C. Test Quality & Observability

- [x] **Missing validation edge-case tests**: Covered in `test_pipe_config_tools.py` (`*_rejects_*__no_integration`).
- [x] **Missing service-layer error propagation test**: `test_create_pipe_propagates_execute_query_errors` in `test_pipe_config_service.py`.
- [x] Fixture hygiene is good — clean fixtures, proper test isolation.
- [x] Integration tests (`test_pipe_config_tools_live.py`) cover full MCP stack with opt-in env vars.

### D. Code Quality & Maintainability

- [x] **DRY violation — error-handling boilerplate**: `handle_pipe_config_tool_graphql_error` in `pipe_config_tool_helpers.py`.
- [x] **Double JSON encoding in success payloads**: `build_pipe_mutation_success_payload` now sets `result` to the raw dict; preview `pipe_summary` remains human-readable JSON text via `_to_readable_json`.

## 4. Improvements & Refactoring (Recommended)

- [x] **DRY — Extract error handler**: `handle_pipe_config_tool_graphql_error` (see `pipe_config_tool_helpers.py`).

```python
def _handle_graphql_error(
    exc: BaseException,
    fallback_msg: str,
    *,
    debug: bool = False,
) -> dict[str, Any]:
    codes = _extract_graphql_error_codes(exc)
    cid = _extract_graphql_correlation_id(exc)
    msgs = _extract_error_strings(exc)
    base = "; ".join(msgs) if msgs else fallback_msg
    return build_pipe_tool_error_payload(
        message=_with_debug_suffix(base, debug=debug, codes=codes, correlation_id=cid),
    )
```

- [x] **Typing — Add `__all__` to `pipe_config_tool_helpers.py`**: Exported public names explicitly.
- [x] **Typing — Consider TypedDict for generic success payload**: `PipeMutationSuccessPayload` added.
- [x] **Readability — Consistent `debug` parameter**: `debug: bool = False` on all pipe-config mutation tools (including `delete_pipe` as before).

## 5. Nitpicks (Optional)

- [x] `_format_json_for_llm` renamed to `_to_readable_json`.
- [x] `_valid_phase_field_id` uses `str | int`.

## 6. Verification Steps

```bash
# Run all unit tests for changed files
uv run pytest tests/services/pipefy/test_pipe_config_service.py \
    tests/tools/test_pipe_config_tools.py \
    tests/services/test_pipefy_facade.py \
    tests/tools/test_registry.py \
    tests/test_server.py -v

# Lint and format check
uv run ruff check src/pipefy_mcp/services/pipefy/pipe_config_service.py \
    src/pipefy_mcp/services/pipefy/queries/pipe_config_queries.py \
    src/pipefy_mcp/tools/pipe_config_tools.py \
    src/pipefy_mcp/tools/pipe_config_tool_helpers.py \
    src/pipefy_mcp/tools/registry.py
uv run ruff format --check src/

# Full test suite (excluding integration)
uv run pytest -m "not integration" -v

# Coverage report for new service
uv run pytest tests/services/pipefy/test_pipe_config_service.py \
    tests/tools/test_pipe_config_tools.py \
    --cov=src/pipefy_mcp/services/pipefy/pipe_config_service \
    --cov=src/pipefy_mcp/tools/pipe_config_tools \
    --cov-report=term-missing
```
