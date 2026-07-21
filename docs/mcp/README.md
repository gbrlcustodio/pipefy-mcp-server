# MCP server documentation

Material in this tree describes **`pipefy-mcp-server`**: the MCP process, tool behavior, and client wiring.

## Contents

| Path | Description |
|------|-------------|
| [`tools/cross-cutting.md`](tools/cross-cutting.md) | Shared conventions: pagination, IDs, `debug`, destructive deletes, permissions, errors |
| [`tools/pipes-and-cards.md`](tools/pipes-and-cards.md) | Pipes, phases, fields, labels, cards, field conditions, card attachments |
| [`tools/database-tables.md`](tools/database-tables.md) | Tables, records, table fields, table-record attachments |
| [`tools/relations.md`](tools/relations.md) | Pipe and card relations |
| [`tools/reports.md`](tools/reports.md) | Pipe and organization reports, async exports |
| [`tools/automations-and-ai.md`](tools/automations-and-ai.md) | Traditional automations, AI automations, AI agents, validators |
| [`tools/llm-providers.md`](tools/llm-providers.md) | LLM providers: discovery (custom + system, vendor models, defaults, dependencies, access probe) and custom-provider management (create/update/delete, active-status, default set/reset) |
| [`tools/knowledge-bases.md`](tools/knowledge-bases.md) | Pipe-scoped AI knowledge bases: list, plain text, document (PDF), and data lookup CRUD, read-access probe |
| [`tools/observability.md`](tools/observability.md) | Logs, usage, credits, execution metrics, job exports |
| [`tools/members-email-webhooks.md`](tools/members-email-webhooks.md) | Membership, inbox email, webhooks |
| [`tools/organization.md`](tools/organization.md) | Organization metadata |
| [`tools/portal.md`](tools/portal.md) | Portals, pages, elements, sub-portals |
| [`tools/ipaas.md`](tools/ipaas.md) | iPaaS (Advanced Automations) tool discovery, invocation, and app connections |
| [`tools/introspection.md`](tools/introspection.md) | Schema discovery and raw GraphQL |

Start with [`tools/cross-cutting.md`](tools/cross-cutting.md) for pagination, IDs, `debug`, permissions, and error shape — then open the domain guide you need.

For install and per-client MCP wiring (hosted HTTP, Cursor, Claude Desktop, Claude Code, Codex), see the root [`README.md#installation`](../../README.md#installation). First-time agent checklist: [`skills/onboarding/pipefy-toolkit-setup/SKILL.md`](../../skills/onboarding/pipefy-toolkit-setup/SKILL.md). For environment variables and `config.toml`, see [`../config.md`](../config.md). Edge cases (`errSecParam`, local `claude mcp add`, `.mcp.json`, local-clone alternative): [`packages/mcp/README.md`](../../packages/mcp/README.md).

The MCP ↔ CLI coverage matrix lives at **[`../parity.md`](../parity.md)**.
