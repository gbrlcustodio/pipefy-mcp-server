# Knowledge bases

Pipe-scoped AI knowledge bases: list every item on a pipe, full CRUD for plain-text and document (PDF) sources, and a read-access probe. **10 tools.**

Knowledge bases are the data sources an AI agent draws on. Each item's `id` is what you attach to an agent or behavior via `dataSourceIds` (see [Automations & AI](automations-and-ai.md)): use `get_ai_knowledge_bases` to discover the IDs, then `validate_ai_agent_behaviors(data_source_ids=[...])` to check membership before writing the agent.

---

| Tool | Read-only | Role |
|------|-----------|------|
| `get_ai_knowledge_bases` | Yes | Lists every knowledge base item on a pipe (plain texts, documents, data lookups) as one flat list — no pagination. Each item carries `id`, `type` (e.g. `knowledge_base_plain_texts`), `name`, `description`, `updatedAt`. |
| `get_ai_knowledge_base_plain_text` | Yes | Fetches one plain text by `id`, including its full `content`. |
| `create_ai_knowledge_base_plain_text` | No | Creates a plain text. `name`, `content` (1-3500 chars), and `description` (1-900 chars) are all required. |
| `update_ai_knowledge_base_plain_text` | No | Partial update by `plain_text_id`: pass any of `name` / `content` / `description` (at least one); omitted fields keep their stored value. |
| `delete_ai_knowledge_base_plain_text` | No | Deletes a plain text permanently. Two-step: preview with `confirm=false` (default), execute with `confirm=true`. |
| `get_ai_knowledge_base_document` | Yes | Fetches one document by `id`. `content` is the stored document URL, not the extracted text. |
| `create_ai_knowledge_base_document` | No | Creates a document from a local PDF in one shot (presigned URL, S3 PUT, create mutation). `name`, `file_path`, and `description` (1-900 chars) are required. |
| `update_ai_knowledge_base_document` | No | Metadata-only partial update by `document_id`: pass `name` and/or `description` (at least one). The PDF file cannot be replaced. |
| `delete_ai_knowledge_base_document` | No | Deletes a document permanently. Two-step: preview with `confirm=false` (default), execute with `confirm=true`. |
| `validate_knowledge_base_access` | Yes | Probes whether the current credential can read a pipe's knowledge bases, classifying failures into structured problems instead of opaque errors. |

## Identifiers: pipe UUID, not numeric ID

Every knowledge base operation is scoped by the pipe **UUID** (`pipe_uuid`), not the numeric pipe ID — this follows the Pipefy GraphQL API. `get_pipe` returns the `uuid` field; `get_ai_knowledge_bases` returns each item's `id` (a data-source UUID) for the plain-text-by-id operations and for `dataSourceIds`.

## Plain-text limits (enforced client-side)

Limits fail fast before the network call, so an over-limit value is rejected with an actionable message rather than a backend 422:

- `content`: required, 1-3500 characters.
- `description`: required, 1-900 characters. The GraphQL schema marks `description` optional, but the backend rejects a blank one, so the toolkit requires it on create.
- `name`: required, non-blank.

On update, only the fields you pass are validated and sent; the others keep their stored values.

## Documents (one-shot PDF upload)

`create_ai_knowledge_base_document` takes a local `file_path` and does the whole upload in one call: read the file, request a presigned URL for the pipe's organization (resolved from the pipe UUID), PUT the bytes to S3, then run the create mutation with the persistent download URL. The MCP server reads the file as the user, so `file_path` is a local path (`~` is expanded); the create tool is therefore not exposed in the remote profile.

Client-side checks fail fast — they are the only guardrail on this path, because the backend skips its own PDF and size validation when a document is supplied as a URL rather than a raw upload:

- `file_path`: must be a `.pdf` (case-insensitive extension), under 20 MiB.
- `name`: required, non-blank.
- `description`: required, 1-900 characters. As with plain text, the GraphQL schema marks it optional but the backend rejects a blank one.

Failures are tagged with the step that failed — `file_read`, `presigned_url`, `s3_upload`, or `kb_create` — carried on `error.details.step` (an S3 failure also carries `body_snippet`).

**Indexing is asynchronous.** A created document is not necessarily searchable by agents the moment the tool returns; vectorization runs in the background.

**Update is metadata-only.** `update_ai_knowledge_base_document` changes `name` / `description`; it cannot replace the PDF. `content` returned by `get_ai_knowledge_base_document` is the stored document URL, not the extracted text.

## Probe semantics and the write gate

- A green `validate_knowledge_base_access` proves **read access only** (`read_ai_agents` on the pipe) — never the `manage_ai_agents` entitlement that plain-text and document create / update / delete require.
- An **empty knowledge base list** is a valid green result (`knowledge_base_count: 0`), not a failure.
- The **CLI gates writes** on the probe: `pipefy kb plain-text create` / `update` and `pipefy kb document create` / `update` run the read-access probe first and fail with the classified problem if it is denied, before attempting the mutation.
- The **MCP tools stay explicit-validate-first**: create / update do not auto-probe. Call `validate_knowledge_base_access` yourself before writing.
- **Deletes require confirmation**: the MCP tool needs `confirm=true`; the CLI needs `--yes` (or an interactive prompt).

## Attaching a source to an agent

`validate_ai_agent_behaviors` accepts an optional `data_source_ids` (agent-level). It is unioned with each behavior's `actionParams.aiBehaviorParams.dataSourceIds` and checked against the pipe's knowledge bases: IDs not present on the pipe produce **warnings only** (`valid` stays true). If the knowledge base list cannot be read, a single warning is added and the membership check is skipped — a read failure is never reported as a broken reference.

## Error classification

Failures on this surface are classified by the shared SDK-level module (`pipefy_sdk.graphql_problem`) into structured problems — `permission_denied`, `not_found`, `invalid_arguments`, `feature_not_enabled`, or `runtime` — carried on `error.details.kind` alongside the GraphQL `extensions.code` and `correlation_id`. The same classifier backs the CLI (`pipefy kb ...`), so both surfaces report the same problem kinds.
