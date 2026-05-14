# Pipefy Skills Catalog

Anthropic Skills-format playbooks for common Pipefy workflows. Each skill is a single Markdown file consumable by any LLM agent (Claude Code, Cursor, Codex, or any assistant that reads Markdown files).

## Using skills

**With the CLI (starter pack):**

```bash
pipefy skills list                        # list bundled skills
pipefy skills show pipes-and-cards        # print skill to stdout
pipefy skills show pipes-and-cards | pbcopy  # copy to clipboard for agent context
```

**From source (full catalog):**

```bash
# Clone once
git clone https://github.com/<owner>/pipefy-labs && cd pipefy-labs

# Point your agent at the skills directory
# In Claude Code: /skills/pipes-and-cards/pipefy-pipes-and-cards/SKILL.md
# In Cursor: add to .cursor/rules or reference in system prompt
```

---

## Catalog

| Domain | Skill | Description |
|--------|-------|-------------|
| **Pipes & Cards** | [pipefy-pipes-and-cards](pipes-and-cards/pipefy-pipes-and-cards/SKILL.md) | Create, read, update, delete pipes, phases, fields, labels, cards, and field conditions. 37 MCP tools. |
| **Database Tables** | [pipefy-database-tables](database-tables/pipefy-database-tables/SKILL.md) | Tables, records, schema columns, and attachments. 17 MCP tools. |
| **Relations** | [pipefy-relations](relations/pipefy-relations/SKILL.md) | Link processes and cards across workflows. 8 MCP tools. |
| **Reports** | [pipefy-reports](reports/pipefy-reports/SKILL.md) | Pipe and org reports: CRUD and async exports. 17 MCP tools. |
| **Automations** | [pipefy-automations](automations/pipefy-automations/SKILL.md) | Traditional automations, AI automations, and simulation. 15 MCP tools. |
| **AI Agents** | [pipefy-ai-agents](ai-agents/pipefy-ai-agents/SKILL.md) | Conversational AI agents with behaviors. 7 MCP tools. |
| **Observability** | [pipefy-observability](observability/pipefy-observability/SKILL.md) | Logs, usage stats, credit consumption, job exports. 10 MCP tools. |
| **Members, Email & Webhooks** | [pipefy-members-email-webhooks](members-email-webhooks/pipefy-members-email-webhooks/SKILL.md) | Membership, email, and webhook management. 11 MCP tools. |
| **Introspection** | [pipefy-introspection](introspection/pipefy-introspection/SKILL.md) | Schema discovery and raw GraphQL fallback (Tier 2). 6 MCP tools. |
| **Process Design** | [pipefy-process-design](process-design/pipefy-process-design/SKILL.md) | Consulting help for designing processes. Use only when asked to architect (not execute). |
| **Process Intelligence** | [pipefy-process-intelligence](process-intelligence/pipefy-process-intelligence/SKILL.md) | Analyze existing pipes for improvement opportunities. |
| **API Fallback** | [pipefy-api-fallback](api-troubleshoot/pipefy-api-fallback/SKILL.md) | Direct GraphQL API fallback (Tier 3 — last resort). |

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the style guide, frontmatter rules, and review rubric.

See [`AGENTS.md`](AGENTS.md) for the full authoring guide and naming conventions.

Provenance from pipeclaw bootstrap: [`docs/pipeclaw-mapping.md`](docs/pipeclaw-mapping.md).
