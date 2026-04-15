# Code Review: feat/tool-surface-hardening-phase-3 vs pipe-full-toolset

## Document meta

| Field | Value |
| :--- | :--- |
| **Review date** | 2026-04-14 |
| **Diff scope** | `pipe-full-toolset...feat/tool-surface-hardening-phase-3` |
| **Branch tip** | `2e59a5f` |
| **pipe-full-toolset tip** | `76c1247` |
| **Diff size** | 14 files changed, 1047 insertions(+), 12 deletions(-) |

## How to use this document (for humans + fix agents)

1. Work through **S5 Required fixes** in **ID order** (`RF-01`, `RF-02`, ...) before **S7 Improvements**.
2. Each finding has **Location**, **Snippet**, and **Suggested direction** -- open the file at that line; do not rely on memory.
3. After each fix (or small batch), run the **Verify** commands for that finding.
4. **Depends on** prevents ordering mistakes when fixes interact.

---

## 0. Context read (checklist)

- [x] PRD: `.cursor/dev-planning/specs/tool-surface-hardening/prd-tool-surface-hardening.md` (FR-10, FR-11, FR-12)
- [x] Tasks: `.cursor/dev-planning/specs/tool-surface-hardening/tasks/tasks-tool-surface-hardening.md` (section 4.0, sub-tasks 4.1-4.10)
- [x] `CLAUDE.md` (architecture, code quality, no-ai-slop, testing rules)
- [x] `.claude/commands/testing-anti-patterns.md` (mock gates, behavior-not-mocks, completeness)

---

## 1. Executive summary

| Category | Status | Summary |
| :--- | :--- | :--- |
| Architecture | pass | Clean layer separation: query in `queries/`, service in `pipe_service.py`, facade delegation in `client.py`, tool in `ai_automation_tools.py`. New helper in `graphql_error_helpers.py` follows existing patterns. |
| Security | pass | No credentials in logs/errors. `ctx.debug()` used for internal diagnostics. Enrichment helper returns `None` on failure (never masks original error). Timeout bounds on all async gather calls. |
| Correctness | warn | Two issues: (1) `create_card` re-raise via `type(exc)(...)` loses `.errors` attribute of `TransportQueryError`; (2) read-only field warnings are unfiltered (noisy on pipes with many non-editable fields). |
| Tests | warn | New features have solid coverage (24 new tests). However: no integration tests for FR-11 enrichment at the tool level (only the helper is unit-tested), and one test helper has unused parameters. |
| Docs / MCP tool UX | pass | Tool docstring is clear with `Args:` block. `readOnlyHint=True` annotation set. Return shape documented. |

**Merge recommendation:** `ready with fixes` -- RF-01 and RF-02 should be addressed before merge. DD findings are non-blocking but should be tracked.

**Counts:** Required fixes: 2 -- Deep dive: 4 -- Improvements: 3 -- Nits: 2

---

## 2. Diff inventory

| Area | Files | PRD / Task |
| :--- | :--- | :--- |
| Pipe preferences query | `queries/pipe_queries.py`, `pipe_service.py`, `client.py` | FR-10 / 4.1 |
| Prompt validation tool | `ai_automation_tools.py`, `ai_tool_helpers.py` | FR-10 / 4.2 |
| Prompt validation tests | `test_ai_automation_tools.py` | FR-10 / 4.3 |
| Permission enrichment helper | `graphql_error_helpers.py` | FR-11 / 4.4 |
| Permission enrichment tests | `test_graphql_error_helpers.py` | FR-11 / 4.5 |
| Cross-pipe enrichment wiring | `ai_agent_tools.py`, `automation_tools.py`, `pipe_tools.py` | FR-11 / 4.6 |
| Proactive membership check | `ai_agent_tools.py` | FR-12 / 4.7 |
| Membership check tests | `test_ai_agent_tools.py` | FR-12 / 4.8 |
| Registry update | `registry.py` | 4.9 |
| Facade delegation test | `test_pipefy_facade.py` | 4.1 (supplementary) |

---

## 3. PRD / spec alignment

| Topic | Expected (doc + section) | Observed in code | Finding ID |
| :--- | :--- | :--- | :--- |
| FR-10: validate_ai_automation_prompt | 5 validations + return `{valid, problems, warnings, field_map}` | All 5 validations present; return shape correct; `readOnlyHint=True` | -- (pass) |
| FR-11: Cross-pipe enrichment | Apply to `create_card`, `create_ai_agent`, `update_ai_agent`, `create_automation` | All four applied; `create_connected_card` flows through `create_ai_agent` behaviors | -- (pass) |
| FR-11: Enrichment graceful failure | "If enrichment fails, return original error unchanged" | Helper returns `None` on timeout/error; callers fall through to original path | -- (pass) |
| FR-11: Always-on (not behind debug) | "Always-on (not behind debug flag)" | Enrichment runs unconditionally in error paths | -- (pass) |
| FR-12: Proactive SA check | Check SA membership on cross-pipe target pipes; add to `problems` | Implemented; adds to `membership_problems` merged into `problems` | -- (pass) |
| FR-12: Skip when SA IDs not configured | "If SA IDs not configured, skip" | Guarded by `if sa_ids and target_pipe_ids` | -- (pass) |
| FR-11: Error message format | `"Service account is not a member of pipe <pipe_id> (<pipe_name>). Use invite_members to add it."` | When `get_pipe_members` raises, message uses `pipe {pid}` (no name); when empty members, includes pipe name | DD-02 |

---

## 4. Prioritized work queue

| Order | ID | Severity | Title | Location |
| :---: | :--- | :--- | :--- | :--- |
| 1 | RF-01 | high | `_pipe_ids_from_behavior` imported as private function across modules | `ai_agent_tools.py:14` |
| 2 | RF-02 | high | `create_card` re-raise via `type(exc)(...)` loses `.errors` attribute | `pipe_tools.py:141` |
| 3 | DD-01 | medium | Read-only field warnings unfiltered -- noisy on pipes with many non-editable fields | `ai_automation_tools.py:178-187` |
| 4 | DD-02 | medium | `enrich_permission_denied_error` asserts "not a member" when `get_pipe_members` raises for any reason | `graphql_error_helpers.py:196-202` |
| 5 | DD-03 | low | Iterating `set[str]` twice for `asyncio.gather` + `zip` is order-dependent | `ai_agent_tools.py:727-735` |
| 6 | DD-04 | low | Deferred import of `settings` inside function body | `ai_agent_tools.py:718` |
| 7 | IM-01 | medium | No integration tests for FR-11 enrichment at tool level | `test_ai_agent_tools.py`, `test_automation_tools.py`, `test_pipe_tools.py` |
| 8 | IM-02 | low | `_pipe_graph_with_fields_for_both` has unused parameters | `test_ai_agent_tools.py:1994` |
| 9 | IM-03 | low | `_cross_pipe_behavior` has unused `source_pipe_id` parameter | `test_ai_agent_tools.py:1968` |

---

## 5. Required fixes (before merge)

### RF-01 -- Private function `_pipe_ids_from_behavior` imported across module boundary

- **Severity:** high
- **Location:** `src/pipefy_mcp/tools/ai_agent_tools.py:14`
- **Snippet:**

```python
from pipefy_mcp.tools.ai_tool_helpers import (
    _pipe_ids_from_behavior,
    build_ai_tool_error,
    ...
)
```

- **Problem:** `_pipe_ids_from_behavior` is a private function (prefixed with `_`) in `ai_tool_helpers.py`. Importing it in `ai_agent_tools.py` crosses the module abstraction boundary. Python convention: `_`-prefixed names are internal to their module. Linters like pyright/pylance flag this, and it signals to other developers that the function's contract is not stable.
- **Trigger / scenario:** Future refactoring of `ai_tool_helpers.py` could rename or change `_pipe_ids_from_behavior` without considering external callers, breaking `ai_agent_tools.py`.
- **Rationale:** CLAUDE.md: "Hide implementation details; expose clear interfaces." The underscore prefix explicitly marks this as internal.
- **PRD / spec link:** Task 4.7 (proactive membership check uses pipe IDs from behaviors).
- **Suggested direction:**
  1. Rename `_pipe_ids_from_behavior` to `pipe_ids_from_behavior` (remove underscore) in `ai_tool_helpers.py`.
  2. Update the import in `ai_agent_tools.py` accordingly.
  3. Alternatively, move `_collect_pipe_ids_from_behaviors` (which wraps it) into `ai_tool_helpers.py` as a public function and import that instead, keeping `_pipe_ids_from_behavior` private.
- **Tests:** Existing tests pass unchanged -- function behavior doesn't change.
- **Verify:**

```bash
uv run ruff check src/pipefy_mcp/tools/ai_tool_helpers.py src/pipefy_mcp/tools/ai_agent_tools.py
uv run pytest tests/tools/test_ai_agent_tools.py -v
```

- **Depends on:** none

---

### RF-02 -- `create_card` re-raise via `type(exc)(...)` loses `.errors` attribute

- **Severity:** high
- **Location:** `src/pipefy_mcp/tools/pipe_tools.py:134-142`
- **Snippet:**

```python
try:
    result = await client.create_card(pipe_id, card_data)
except Exception as exc:  # noqa: BLE001
    perm_msg = await enrich_permission_denied_error(
        exc, [str(pipe_id)], client
    )
    if perm_msg:
        raise type(exc)(f"{perm_msg}\n{exc}") from exc
    raise
```

- **Problem:** `type(exc)(f"{perm_msg}\n{exc}")` creates a new `TransportQueryError` with only the `msg` argument. The original `.errors` list (containing GraphQL error details, extensions, codes) is lost. This also differs from the enrichment pattern used in `ai_agent_tools.py` and `automation_tools.py`, where enrichment is prepended to a returned error payload rather than re-raised.
- **Trigger / scenario:** Any `PERMISSION_DENIED` error from `create_card` where enrichment succeeds. The re-raised exception lacks `.errors`, so any downstream code calling `extract_graphql_error_codes()` or `extract_error_strings()` on the re-raised exception will get incomplete results.
- **Rationale:** Inconsistent error handling pattern across tools; potential data loss in exception attributes. The other enrichment sites (ai_agent_tools, automation_tools) return error payloads directly, which is safer.
- **PRD / spec link:** FR-11 / Task 4.6.
- **Suggested direction:**
  1. Wrap the `client.create_card` call in a try/except that catches `Exception`, calls enrichment, and returns an error dict (consistent with other tools).
  2. Use the existing `handle_tool_graphql_error` or `build_ai_tool_error` pattern to return a structured error payload with the enrichment prepended.
- **Proposed fix:**

```python
try:
    result = await client.create_card(pipe_id, card_data)
except Exception as exc:  # noqa: BLE001
    perm_msg = await enrich_permission_denied_error(
        exc, [str(pipe_id)], client
    )
    error_text = str(exc)
    if perm_msg:
        error_text = f"{perm_msg}\n{error_text}"
    return {"success": False, "error": error_text}
```

- **Tests:** Add a test in `test_pipe_tools.py` for `create_card` with a `PERMISSION_DENIED` error to verify the enriched error payload structure.
- **Verify:**

```bash
uv run pytest tests/tools/test_pipe_tools.py -v
uv run pytest tests/tools/test_ai_automation_tools.py -k validate -v
```

- **Depends on:** none

---

## 6. Deep dive findings (non-blocking but should track)

### DD-01 -- Read-only field warnings unfiltered

- **Severity:** medium
- **Location:** `src/pipefy_mcp/tools/ai_automation_tools.py:178-187`
- **Snippet:**

```python
for field in phase.get("fields") or []:
    fid = str(field.get("internal_id") or field.get("id", ""))
    label = field.get("label", "")
    if fid:
        all_field_ids.add(fid)
        field_map[fid] = label
    if field.get("editable") is False:
        warnings.append(f"Field {fid} ({label}) is read-only.")
```

- **Problem:** ALL read-only fields in the pipe generate a warning, regardless of whether the prompt or `field_ids` reference them. A pipe with 20 non-editable fields produces 20 warnings even when the prompt uses only one editable field.
- **Trigger / scenario:** Any pipe with system fields (created_at, updated_at, etc.) or locked fields.
- **Rationale:** Noisy warnings reduce signal-to-noise ratio and may cause agents to waste time investigating irrelevant warnings.
- **Suggested direction:** Defer the read-only check until after all field IDs are collected. Only warn for fields that appear in `prompt_tokens` or `field_ids`:

```python
# After building all_field_ids and field_map:
for fid in set(prompt_tokens) | set(str(f) for f in field_ids):
    if fid in all_field_ids and fid in readonly_fields:
        warnings.append(f"Field {fid} ({field_map.get(fid, '')}) is read-only.")
```

- **Tests:** Update `test_read_only_field_warning` to also assert that unreferenced read-only fields do NOT produce warnings.
- **Verify:** `uv run pytest tests/tools/test_ai_automation_tools.py -k "read_only" -v`
- **Depends on:** none

---

### DD-02 -- False positive in enrichment when `get_pipe_members` raises

- **Severity:** medium
- **Location:** `src/pipefy_mcp/tools/graphql_error_helpers.py:196-202`
- **Snippet:**

```python
if isinstance(result, BaseException):
    # Could not fetch members for this pipe -- likely the pipe we lack access to
    pipe_name = f"pipe {pid}"
    missing_pipes.append(
        f"Service account is not a member of {pipe_name}. "
        f"Use invite_members to add it."
    )
    continue
```

- **Problem:** When `get_pipe_members` raises for a pipe, the code assumes "not a member" and reports it. But the exception could be a network timeout, a transient API error, or the pipe not existing. The message asserts a definitive cause ("is not a member") when the actual cause is uncertain.
- **Trigger / scenario:** Transient network error on `get_pipe_members` during a PERMISSION_DENIED enrichment attempt.
- **Rationale:** Could mislead agents into adding members to pipes where the real issue is network instability. The PRD says enrichment message should identify "which pipe lacks membership" -- but only when we actually know membership is the issue.
- **Suggested direction:** Soften the message for exception cases to indicate uncertainty:

```python
if isinstance(result, BaseException):
    missing_pipes.append(
        f"Could not verify membership for pipe {pid} ({result}). "
        f"Check if the service account is a member — use invite_members if not."
    )
```

- **Tests:** Update `test_permission_denied_missing_member_returns_enrichment` assertion to match new message.
- **Verify:** `uv run pytest tests/tools/test_graphql_error_helpers.py -v`
- **Depends on:** none

---

### DD-03 -- Set iteration order relied upon for `asyncio.gather` + `zip`

- **Severity:** low
- **Location:** `src/pipefy_mcp/tools/ai_agent_tools.py:727-735`
- **Snippet:**

```python
member_results = await asyncio.wait_for(
    asyncio.gather(
        *(client.get_pipe_members(tpid) for tpid in target_pipe_ids),
        return_exceptions=True,
    ),
    timeout=MEMBERSHIP_CHECK_TIMEOUT_SECONDS,
)
for tpid, mresult in zip(target_pipe_ids, member_results):
```

- **Problem:** `target_pipe_ids` is a `set[str]`. The code relies on iterating it twice in the same order (once for `gather`, once for `zip`). Python guarantees this for an unmodified set object, but the intent is not obvious and fragile under refactoring.
- **Suggested direction:** Convert to a list before the first use: `target_list = list(target_pipe_ids)` and use `target_list` for both `gather` and `zip`.
- **Depends on:** none

---

### DD-04 -- Deferred import of `settings` inside function body

- **Severity:** low
- **Location:** `src/pipefy_mcp/tools/ai_agent_tools.py:718`
- **Snippet:**

```python
# Inside validate_ai_agent_behaviors tool function:
from pipefy_mcp.settings import settings
```

- **Problem:** Import inside function body rather than at module level. This pattern is sometimes used to avoid circular imports, but `pipefy_mcp.settings` has no circular dependency with `ai_agent_tools.py`. Other tools (e.g. `member_tools.py:12`) import it at module level.
- **Suggested direction:** Move to module-level imports for consistency with the rest of the codebase.
- **Depends on:** none

---

## 7. Improvements (recommended)

### IM-01 -- Missing integration tests for FR-11 enrichment at tool level

- **Severity:** medium
- **Location:** `tests/tools/test_ai_agent_tools.py`, `tests/tools/test_automation_tools.py`, `tests/tools/test_pipe_tools.py`
- **Problem:** The `enrich_permission_denied_error` helper has 7 unit tests (test_graphql_error_helpers.py), but the wiring in `create_ai_agent`, `update_ai_agent`, `create_automation`, and `create_card` has no tests that verify the enriched message appears in the tool's error payload when a PERMISSION_DENIED error occurs.
- **Rationale:** Testing anti-patterns doc: "New logic paths have sad path tests, not only happy path." The integration between helper and tool error paths is untested.
- **Suggested direction:** Add at least one test per enriched tool that:
  1. Mocks the service call to raise a `TransportQueryError` with `PERMISSION_DENIED`
  2. Mocks `get_pipe_members` to return members for one pipe but raise for another
  3. Asserts the enriched message appears in the error payload
- **Depends on:** RF-02 (create_card pattern must be decided first)

---

### IM-02 -- `_pipe_graph_with_fields_for_both` has unused parameters

- **Severity:** low
- **Location:** `tests/tools/test_ai_agent_tools.py:1994`
- **Snippet:**

```python
def _pipe_graph_with_fields_for_both(source_pipe_id="1", target_pipe_id="999"):
    """Pipe graph and relations enabling cross-pipe validation."""
    return {
        "pipe": {
            "phases": [{"id": "ph-1", "fields": [{"id": "100"}]}],
            "start_form_fields": [],
        }
    }
```

- **Problem:** Both `source_pipe_id` and `target_pipe_id` parameters are declared but never used in the function body. This is dead code in tests.
- **Suggested direction:** Remove the unused parameters: `def _pipe_graph_with_fields_for_both():`.
- **Depends on:** none

---

### IM-03 -- `_cross_pipe_behavior` has unused `source_pipe_id` parameter

- **Severity:** low
- **Location:** `tests/tools/test_ai_agent_tools.py:1968`
- **Snippet:**

```python
def _cross_pipe_behavior(source_pipe_id="1", target_pipe_id="999"):
```

- **Problem:** `source_pipe_id` is never used in the function body (only `target_pipe_id` is used in `"pipeId": target_pipe_id`).
- **Suggested direction:** Remove: `def _cross_pipe_behavior(target_pipe_id="999"):`.
- **Depends on:** none

---

## 8. Nits

| ID | Location | Note |
| :--- | :--- | :--- |
| NIT-01 | `ai_agent_tools.py:39` | `MEMBERSHIP_CHECK_TIMEOUT_SECONDS = 5` placed before `VALIDATE_FETCH_TIMEOUT_SECONDS = 30` -- reverse alphabetical and conceptual grouping. Consider placing after `VALIDATE_FETCH_TIMEOUT_SECONDS` since membership check runs inside the validation tool flow. |
| NIT-02 | `graphql_error_helpers.py:208` | `" | ".join(missing_pipes)` uses pipe character as separator. When multiple pipes are missing, this produces a single-line message that's harder to parse. Consider `"\n"` for multi-pipe cases. |

---

## 9. Verification (full suite)

Commands run during review:

```bash
git diff pipe-full-toolset...HEAD --stat
# 14 files changed, 1047 insertions(+), 12 deletions(-)

uv run pytest -m "not integration" -v
# 1458 passed, 29 deselected in 27.10s

uv run ruff check src/ tests/
# All checks passed!

uv run ruff format --check src/ tests/
# 162 files already formatted
```

---

## 10. Appendix -- Files touched in diff

```
src/pipefy_mcp/services/pipefy/client.py                     (+4)
src/pipefy_mcp/services/pipefy/pipe_service.py                (+10)
src/pipefy_mcp/services/pipefy/queries/pipe_queries.py        (+34)
src/pipefy_mcp/tools/ai_agent_tools.py                        (+86, -1)
src/pipefy_mcp/tools/ai_automation_tools.py                   (+140, -1)
src/pipefy_mcp/tools/ai_tool_helpers.py                       (+30)
src/pipefy_mcp/tools/automation_tools.py                      (+11)
src/pipefy_mcp/tools/graphql_error_helpers.py                 (+75, -1)
src/pipefy_mcp/tools/pipe_tools.py                            (+11, -1)
src/pipefy_mcp/tools/registry.py                              (+1)
tests/services/test_pipefy_facade.py                          (+6)
tests/tools/test_ai_agent_tools.py                            (+209)
tests/tools/test_ai_automation_tools.py                       (+325)
tests/tools/test_graphql_error_helpers.py                     (+117, new file)
```
