# iPaaS (Advanced Automations)

Discover and invoke the iPaaS tools available to a pipe's workspace. **2 tools.**

---

| Tool | Read-only | Role |
|------|-----------|------|
| `get_ipaas_tools` | Yes | Lists the iPaaS (Advanced Automations) tools available for a pipe; with `tool_name`, expands one tool's full description and input schema. |
| `call_ipaas_tool` | No | Invokes one iPaaS tool by name with `arguments` matching its input schema, relaying the result in full. The catalog includes destructive operations (deleting flows, tables, records) — reserve those for explicit user intent. |

**`pipe_id`** matches GraphQL: use a **string** (unquoted JSON integers are coerced). See [Pipefy IDs in pipes & cards](pipes-and-cards.md#pipefy-ids-type-safety).

## The meta-tool pattern

iPaaS exposes a large catalog (flow building, testing, tables, runs — dozens of
tools, some with very large input schemas). Loading everything into an agent's
context would crowd it out, so the surface is discover → expand → call:

1. `get_ipaas_tools(pipe_id)` — compact catalog: each tool's `name` and the
   first line of its description.
2. `get_ipaas_tools(pipe_id, tool_name="...")` — one tool's full description
   and `inputSchema`, fetched right before you need it.
3. `call_ipaas_tool(pipe_id, tool_name="...", arguments={...})` — invokes the
   tool. Arguments are forwarded verbatim; the iPaaS host validates them
   against its own schema and its error messages are relayed back.

Never expand more than the tool you are about to use. Long-running executions
(flow tests, retries) may still be in flight when the call returns — inspect
progress with the catalog's run-listing tools instead of re-invoking. See
[`docs/ipaas.md`](../../ipaas.md) for the flow overview and vocabulary.

## Requirements

- The caller must be allowed to **create automations on the pipe** (pipe-admin
  ability); the organization must have **iPaaS enabled**.
- No server configuration is needed against production: the deployment defaults
  to Pipefy's canonical public OAuth client (see
  [`docs/config.md`](../../config.md)). Staging/single-tenant hosts override
  `PIPEFY_IPAAS_URL` + `PIPEFY_IPAAS_OAUTH_CLIENT_ID`; a blank client id
  disables both tools, which then answer with a clear "disabled" error.

## Scoping

Each pipe has its own iPaaS workspace: the catalog (and any flows exposed as
tools) is per-pipe, so the same call against two pipes can differ. Flows may
orchestrate across pipes, but they live in exactly one pipe's workspace.
