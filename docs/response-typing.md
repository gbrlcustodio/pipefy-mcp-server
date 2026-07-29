# Response-side typing: parse vs TypedDict

The input side of the toolkit is typed into validating Pydantic models at the boundary, because the API enforces input shapes and a wrong wire name is a hard failure. The response side is different: the shape of a payload is set by *our own* query documents, so a `TypedDict` that merely describes a shape is often enough. This note records where parsing a response into a validating model actually pays off and where it would be over-engineering.

## The decision rule

Parse a response into a validating model only when a consumer currently **re-derives an invariant the payload already guarantees** — the classic sign is a defensive `isinstance` ladder or repeated `.get()` probing of a nested shape that a model could assert once. Two other triggers: a dual-read that masks two query documents disagreeing on key style (align the queries first), or a discriminated union whose branch a consumer must resolve.

Leave a response as a `TypedDict` when it is **pass-through to a serializer** — handed to a formatter or returned in a tool envelope with no field walking. A validating model there guards nothing; it is the over-engineering this typing effort is meant to avoid.

## Boundary catalog

Two kinds of `TypedDict` live in the services and tool layers.

**MCP tool-output envelopes** (`packages/mcp/src/pipefy_mcp/tools/*_tool_helpers.py`, `pagination_helpers.py`) — the `*ReadSuccessPayload` / `*MutationSuccessPayload` / `*ErrorPayload` shells. Each stores the raw GraphQL `data` / `result` dict verbatim inside a `{success, message, …}` shell and returns it to the serializer; the builder never inspects the payload's fields. **Verdict: leave as `TypedDict` — every one of these is a pass-through serializer shell.** The only envelope helper that walks a payload is the pagination lift (`table_tool_helpers._extract_pagination`, `pagination_helpers.build_pagination_info`), which narrows `pageInfo` for output and re-derives no invariant.

**SDK GraphQL read-models** (`packages/sdk/src/pipefy_sdk/services/types.py`, `services/automation_graphql_types.py`) — the real response shapes. The provider, knowledge-base, `me`, and agent payloads in `types.py`, and the automation catalog / summary / simulation / mutation records in `automation_graphql_types.py`, are all consumed pass-through into envelopes or normalized write-result dicts. **Verdict: leave as `TypedDict`.** Two shapes carry an "exactly one populated" discriminant (`ActiveLlmProviderPayload`'s `llmProviderId` / `systemLlmProviderId`; `LlmProviderPayload`'s custom/system union) that no consumer resolves today — parse only if a consumer starts branching on the discriminant.

## The one parse candidate

`AutomationRuleRecord` (`automation_graphql_types.py`) is the single response shape a consumer re-walks defensively. `pipe_config_tool_helpers._automation_mentions_phase` guards each nested `event_params` / `action_params` block with `isinstance` and probes `fromPhaseId` / `inPhaseId` / `to_phase_id` / `phase.id` to re-derive "does this automation reference phase X"; `_filter_automations_by_phase` and `_automations_referencing_phase` re-`.get()` the same records. The record arrives as a raw `dict[str, Any]` from `get_automation`, so the typed shape is declared but never received as a validated object — hence the defensive re-walk.

A validating model would collapse that `isinstance` ladder. The payoff is **modest**: this feeds only the delete-preview "dependents" heuristic, not a correctness-critical path. Recommended as an optional follow-up, not a blocker.

## Follow-up candidates

- **Parse `AutomationRuleRecord`** for the phase-reference heuristic in `pipe_config_tool_helpers.py`, replacing the `isinstance` ladder in `_automation_mentions_phase` with typed attribute reads. Reuse the nested `AutomationEventParamsInput` / `AutomationActionParamsInput` models where the shapes align. Modest payoff (delete-preview only).
- **`_behavior_data_source_ids`** (`ai_preflight.py`) still reads caller-supplied behavior dicts with casing dual-reads (`actionParams`/`action_params`, `dataSourceIds`/`data_source_ids`). This is **request-side**, not a response boundary, so it is outside this survey — but it is a dual-read the input-side typing already makes removable via `BehaviorPayload` (`payload.action_params.ai_behavior_params.data_source_ids`). Worth a small follow-up.

## Bottom line

No response-side casing dual-reads remain, and the query documents agree on key style, so no query alignment is outstanding. The MCP envelope layer is a clean pass-through boundary that should stay `TypedDict`. Response typing pays off in exactly one place, and only modestly; the higher-value typing work was on the input side, where the API enforces the contract.
