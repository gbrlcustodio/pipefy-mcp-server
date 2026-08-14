# Cross-cutting tool behavior

Conventions shared across many MCP tools. Per-area details (parameters, edge cases) stay in the guides linked from the [main README](../../../README.md#mcp-server).

## Pagination

List-style tools accept `first` and `after`. Continue with `pageInfo.endCursor` while `pageInfo.hasNextPage` is true.

## IDs

Pipefy GraphQL uses string IDs. Pass IDs as strings (e.g. `"301234"`). Some parameters also accept JSON integers; the server normalizes to string before calling the API. Success payloads return string IDs. Empty, zero, or otherwise invalid IDs fail validation before any network call.

Which **form** each tool expects (slug vs `internal_id` vs uuid vs numeric id) is the canonical [Identifiers map](identifiers.md#the-four-forms). Type-safety and coercion detail: [Pipefy IDs and type safety](pipes-and-cards.md#pipefy-ids-type-safety).

## `debug=true`

On failures, error text may include GraphQL codes and a `correlation_id` for support.

## `extra_input`

Optional map of extra mutation fields (camelCase keys). Keys that duplicate the tool’s primary parameters are ignored.

## Destructive operations

MCP destructive operations are server-enforced two-step. The first call, with default `confirm=false` or with `confirm=true` and no valid token, does not mutate. It returns a preview whose payload includes a top-level `confirmation_token`, and the same token appears in `message`. The second call must set `confirm=true` and echo that `confirmation_token`. A one-shot `confirm=true` with no token still returns the preview.

The token binds to one tool, one resource identity, and one caller. It is HMAC-signed and replayable within a 300-second TTL; the server does not store it. Hosted verify is stateless HMAC derived from the bearer, so any replica can check the same ticket.

This is not a human click. A client that auto-approves tool calls can preview and confirm back to back with no human involved. The guarantee is that the preview reached the transcript, nothing more.

`execute_graphql` queries stay ungated. Mutations need the same ticket. Do not set `destructiveHint` on `execute_graphql`. Tokens are replayable, so a non-idempotent mutation can run twice if resent within the TTL. Prefer dedicated tools for those writes.

`call_ipaas_tool` is gated when the **call** is judged destructive, in this order: catalog `annotations.destructiveHint` true, then `arguments.operation` case-insensitive equality against the needles `delete`, `remove`, `destroy`, `drop`, `uninstall`, `revoke`, then annotation false stops, else the catalog name is matched as a substring against those same needles. Mixed manage calls with `operation=DELETE` are two-step; `ADD` and `UPDATE` stay one-shot. Do not invent extra needles.

CLI `--yes` is unchanged: no tokens on CLI. `unpublish_sub_portal` stays ungated.

Some destructive tools can attach extra **dependents** context in the preview when optional scope arguments are provided (e.g. `pipe_id` for `delete_label` / `delete_phase`, `phase_id` for `delete_phase_field`) so agents see related automations, field conditions, or label usage before confirming.

## `PERMISSION_DENIED` enrichment

On cross-pipe operations (relations, AI agents), errors carrying `extensions.code = PERMISSION_DENIED` are enriched with a membership hint pointing to `invite_members` when the service account is missing from the target pipe. Runs automatically (no `debug=true` required); implementation in [`enrich_permission_denied_error`](../../../packages/mcp/src/pipefy_mcp/tools/graphql_error_helpers.py).

### Card reads and `PERMISSION_DENIED`

Pipefy often returns **`PERMISSION_DENIED`** for `card(id: …)` when the card was **deleted** or the token cannot see it — the API does not always distinguish those cases. After a successful `delete_card`, `pipefy card get` may still surface `PERMISSION_DENIED` for that id; treat it as “inaccessible or removed,” not necessarily a failed delete. The CLI adds a short hint on `pipefy card get` when this code appears.

## Pre-flight validation for AI features

Before creating/updating AI automations or AI agents, call [`validate_ai_automation_prompt`](automations-and-ai.md#ai-automations) and [`validate_ai_agent_behaviors`](automations-and-ai.md#ai-agent-read-delete) to catch prompt, field, and event errors and membership gaps without round-tripping the write mutation.

## Introspection

`introspect_type`, `introspect_query`, and `introspect_mutation` expose live schema; `search_schema` lists types by keyword (optional `kind` filter). Use `max_depth` where supported to expand nested types in one round trip. Set `include_parsed=true` to also receive a `data` dict for programmatic access.

## Error payloads

When a GraphQL exception carries a structured `errors` list, error payloads return the extracted `message` strings (without a noisy `str(exc)` wrapper that would include `locations` / `extensions`). The raw string is used as a fallback only when no structured messages can be extracted.
