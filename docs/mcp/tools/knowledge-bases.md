# Knowledge bases

Pipe-scoped AI knowledge bases: list every item on a pipe, full CRUD for plain-text sources, and a read-access probe. **6 tools.**

Knowledge bases are the data sources an AI agent draws on. Each item's `id` is what you attach to an agent or behavior via `dataSourceIds` (see [Automations & AI](automations-and-ai.md)): use `get_ai_knowledge_bases` to discover the IDs, then `validate_ai_agent_behaviors(data_source_ids=[...])` to check membership before writing the agent.

---

| Tool | Read-only | Role |
|------|-----------|------|
| `get_ai_knowledge_bases` | Yes | Lists every knowledge base item on a pipe (plain texts, documents, data lookups) as one flat list — no pagination. Each item carries `id`, `type` (e.g. `knowledge_base_plain_texts`), `name`, `description`, `updatedAt`. |
| `get_ai_knowledge_base_plain_text` | Yes | Fetches one plain text by `id`, including its full `content`. |
| `create_ai_knowledge_base_plain_text` | No | Creates a plain text. `name`, `content` (1-3500 chars), and `description` (1-900 chars) are all required. |
| `update_ai_knowledge_base_plain_text` | No | Partial update by `plain_text_id`: pass any of `name` / `content` / `description` (at least one); omitted fields keep their stored value. |
| `delete_ai_knowledge_base_plain_text` | No | Deletes a plain text permanently. Two-step: preview with `confirm=false` (default), execute with `confirm=true`. |
| `validate_knowledge_base_access` | Yes | Probes whether the current credential can read a pipe's knowledge bases, classifying failures into structured problems instead of opaque errors. |

## Identifiers: pipe UUID, not numeric ID

Every knowledge base operation is scoped by the pipe **UUID** (`pipe_uuid`), not the numeric pipe ID — this follows the Pipefy GraphQL API. `get_pipe` returns the `uuid` field; `get_ai_knowledge_bases` returns each item's `id` (a data-source UUID) for the plain-text-by-id operations and for `dataSourceIds`.

## Plain-text limits (enforced client-side)

Limits fail fast before the network call, so an over-limit value is rejected with an actionable message rather than a backend 422:

- `content`: required, 1-3500 characters.
- `description`: required, 1-900 characters. The GraphQL schema marks `description` optional, but the backend rejects a blank one, so the toolkit requires it on create.
- `name`: required, non-blank.

On update, only the fields you pass are validated and sent; the others keep their stored values.

## Probe semantics and the write gate

- A green `validate_knowledge_base_access` proves **read access only** (`read_ai_agents` on the pipe) — never the `manage_ai_agents` entitlement that plain-text create / update / delete require.
- An **empty knowledge base list** is a valid green result (`knowledge_base_count: 0`), not a failure.
- The **CLI gates writes** on the probe: `pipefy kb plain-text create` / `update` run the read-access probe first and fail with the classified problem if it is denied, before attempting the mutation.
- The **MCP tools stay explicit-validate-first**: create / update do not auto-probe. Call `validate_knowledge_base_access` yourself before writing.
- **Deletes require confirmation**: the MCP tool needs `confirm=true`; the CLI needs `--yes` (or an interactive prompt).

## Attaching a source to an agent

`validate_ai_agent_behaviors` accepts an optional `data_source_ids` (agent-level). It is unioned with each behavior's `actionParams.aiBehaviorParams.dataSourceIds` and checked against the pipe's knowledge bases: IDs not present on the pipe produce **warnings only** (`valid` stays true). If the knowledge base list cannot be read, a single warning is added and the membership check is skipped — a read failure is never reported as a broken reference.

## Error classification

Failures on this surface are classified by the shared SDK-level module (`pipefy_sdk.graphql_problem`) into structured problems — `permission_denied`, `not_found`, `invalid_arguments`, `feature_not_enabled`, or `runtime` — carried on `error.details.kind` alongside the GraphQL `extensions.code` and `correlation_id`. The same classifier backs the CLI (`pipefy kb ...`), so both surfaces report the same problem kinds.
