# Cross-cutting tool behavior

Conventions shared across many MCP tools. Per-area details (parameters, edge cases) stay in the guides linked from the [main README](../../README.md#mcp-tools).

## Pagination

List-style tools accept `first` and `after`. Continue with `pageInfo.endCursor` while `pageInfo.hasNextPage` is true.

## IDs

Pipefy GraphQL uses string IDs. Pass IDs as strings (e.g. `"301234"`). Some parameters also accept JSON integers; the server normalizes to string before calling the API. Success payloads return string IDs. Empty, zero, or otherwise invalid IDs fail validation before any network call.

More detail: [Pipefy IDs and type safety](pipes-and-cards.md#pipefy-ids-type-safety).

## `debug=true`

On failures, error text may include GraphQL codes and a `correlation_id` for support.

## `extra_input`

Optional map of extra mutation fields (camelCase keys). Keys that duplicate the tool’s primary parameters are ignored.

## Destructive operations

Deletes use a two-step contract: call with `confirm=false` (default) for a preview, then `confirm=true` only after explicit approval to execute.

Some destructive tools can attach extra **dependents** context in the preview when optional scope arguments are provided (e.g. `pipe_id` for `delete_label` / `delete_phase`, `phase_id` for `delete_phase_field`) so agents see related automations, field conditions, or label usage before confirming.

## `PERMISSION_DENIED` enrichment

On cross-pipe operations (relations, AI agents), errors carrying `extensions.code = PERMISSION_DENIED` are enriched with a membership hint pointing to `invite_members` when the service account is missing from the target pipe. Runs automatically (no `debug=true` required); implementation in [`enrich_permission_denied_error`](../../src/pipefy_mcp/tools/graphql_error_helpers.py).

## Service account protection

When the optional `PIPEFY_SERVICE_ACCOUNT_IDS` env var is set (see [`.env.example`](../../.env.example)), the server guards `remove_member_from_pipe` and `set_role` against locking the service account out of its own pipes. Full contract: [Service account protection](members-email-webhooks.md#service-account-protection).

## Pre-flight validation for AI features

Before creating/updating AI automations or AI agents, call [`validate_ai_automation_prompt`](automations-and-ai.md#ai-automations) and [`validate_ai_agent_behaviors`](automations-and-ai.md#ai-agent-read--delete) to catch prompt, field, and event errors and membership gaps without round-tripping the write mutation.

## Introspection

`introspect_type`, `introspect_query`, and `introspect_mutation` expose live schema; `search_schema` lists types by keyword (optional `kind` filter). Use `max_depth` where supported to expand nested types in one round trip. Set `include_parsed=true` to also receive a `data` dict for programmatic access.

## Error payloads

When a GraphQL exception carries a structured `errors` list, error payloads return the extracted `message` strings (without a noisy `str(exc)` wrapper that would include `locations` / `extensions`). The raw string is used as a fallback only when no structured messages can be extracted.
