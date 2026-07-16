# iPaaS (Advanced Automations)

Discover and invoke the iPaaS tools available to a pipe's workspace, and connect the apps those tools orchestrate. **4 tools.**

---

| Tool | Read-only | Role |
|------|-----------|------|
| `get_ipaas_tools` | Yes | Lists the iPaaS (Advanced Automations) tools available for a pipe; with `tool_name`, expands one tool's full description and input schema. |
| `call_ipaas_tool` | No | Invokes one iPaaS tool by name with `arguments` matching its input schema, relaying the result in full. The catalog includes destructive operations (deleting flows, tables, records) — reserve those for explicit user intent. |
| `get_ipaas_connection_auth_url` | Yes | Step 1 for OAuth-based apps: returns the consent URL the user opens in a browser, plus a `completion` bundle for step 2. |
| `create_ipaas_connection` | No | Creates (or, on an existing `external_id`, rotates) an app connection in the pipe's workspace — token/API-key credentials directly, or OAuth via the two-step flow. |

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

## Connections

Flow steps that act on an external app need a **connection** (the app credential,
stored in the pipe's iPaaS workspace). Before creating one, list what exists
(the catalog's connection-listing tool) and prefer reuse — when several
candidates serve the same piece, agents should name them and ask the user rather
than pick silently.

Two creation paths:

- **Token / API-key pieces** — one `create_ipaas_connection` call with
  `connection_type` (`SECRET_TEXT`, `BASIC_AUTH`, or `CUSTOM_AUTH`) and `value`
  matching the piece's auth props. A literal secret passed this way transits the
  conversation — including the model vendor's API. Users who don't accept that
  trade-off can store the secret in the MCP server's environment and reference
  it as `{"$env": "PIPEFY_IPAAS_CONNECTION_<NAME>"}` instead: only variables
  under that prefix resolve, and the value never enters the conversation. The
  variable must be set before the server starts (e.g. the `env` block of its
  MCP configuration).
- **OAuth pieces** — `get_ipaas_connection_auth_url` returns a consent URL and a
  `completion` bundle; the user opens the URL, authorizes, and pastes back the
  redirect URL they land on; `create_ipaas_connection` finishes with
  `oauth={completion, authorization_response}`. The durable tokens are exchanged
  and stored host-side — no lasting secret ever enters the conversation. This
  path requires the deployment to have an OAuth client configured for the piece;
  when it doesn't, the tool says so and the token path (or the product UI)
  remains.

Creation is an **upsert on `external_id`**: omitting it creates a fresh
connection; passing an existing connection's `external_id` replaces its
credential in place (rotation). Credentials are validated by the iPaaS host at
creation time, so a bad token fails immediately with the host's own message.

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
