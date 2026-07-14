# iPaaS (Advanced Automations)

Discover the iPaaS tool catalog available to a pipe's workspace. **1 tool.**

---

| Tool | Read-only | Role |
|------|-----------|------|
| `get_ipaas_tools` | Yes | Lists the iPaaS (Advanced Automations) tools available for a pipe; with `tool_name`, expands one tool's full description and input schema. |

**`pipe_id`** matches GraphQL: use a **string** (unquoted JSON integers are coerced). See [Pipefy IDs in pipes & cards](pipes-and-cards.md#pipefy-ids-type-safety).

## The meta-tool pattern

iPaaS exposes a large catalog (flow building, testing, tables, runs — dozens of
tools, some with very large input schemas). Loading everything into an agent's
context would crowd it out, so discovery is two-step:

1. `get_ipaas_tools(pipe_id)` — compact catalog: each tool's `name` and the
   first line of its description.
2. `get_ipaas_tools(pipe_id, tool_name="...")` — one tool's full description
   and `inputSchema`, fetched right before you need it.

Never expand more than the tool you are about to use. See
[`docs/ipaas.md`](../../ipaas.md) for the flow overview and vocabulary.

## Requirements

- The caller must be allowed to **create automations on the pipe** (pipe-admin
  ability); the organization must have **iPaaS enabled**.
- The server deployment must have iPaaS credentials configured
  (`PIPEFY_IPAAS_OAUTH_CLIENT_ID` / `PIPEFY_IPAAS_OAUTH_CLIENT_SECRET`, see
  [`docs/config.md`](../../config.md)). Without them the tool answers with a
  clear "not configured" error instead of failing registration.

## Scoping

Each pipe has its own iPaaS workspace: the catalog (and any flows exposed as
tools) is per-pipe, so the same call against two pipes can differ. Flows may
orchestrate across pipes, but they live in exactly one pipe's workspace.
