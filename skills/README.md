# Pipefy skills catalog

Markdown playbooks in **Anthropic Skills** format: each file describes a Pipefy workflow (prerequisites, tools, steps, success criteria). Any agent that reads project files can use them (Cursor, Claude Code, Codex, and others).

## Using the catalog

**Install via [`skills.sh`](https://github.com/vercel-labs/skills)** (55+ agent targets — Claude Code, Cursor, Codex, OpenCode, …):

```bash
npx skills add gbrlcustodio/pipefy-mcp-server                           # all skills
npx skills add gbrlcustodio/pipefy-mcp-server --skill pipefy-pipes-and-cards
npx skills add gbrlcustodio/pipefy-mcp-server -g -a claude-code -y      # CI-friendly
```

`skills.sh` reads canonical `skills/**/SKILL.md` files directly from this repo; no install or wheel needed.

**Reference from source (no install):**

```bash
git clone https://github.com/gbrlcustodio/pipefy-mcp-server.git
# Reference paths such as skills/pipes-and-cards/pipefy-pipes-and-cards/SKILL.md
# in your IDE rules or agent context.
```

---

## Catalog

| Domain | Skill | Description |
|--------|-------|-------------|
| **Pipes & Cards** | [pipefy-pipes-and-cards](pipes-and-cards/pipefy-pipes-and-cards/SKILL.md) | Pipes, phases, fields, labels, cards, field conditions. 37 MCP tools. |
| **Database Tables** | [pipefy-database-tables](database-tables/pipefy-database-tables/SKILL.md) | Tables, records, schema, attachments. 17 MCP tools. |
| **Relations** | [pipefy-relations](relations/pipefy-relations/SKILL.md) | Pipe and card relations. 8 MCP tools. |
| **Reports** | [pipefy-reports](reports/pipefy-reports/SKILL.md) | Pipe and organization reports, async exports. 17 MCP tools. |
| **Automations** | [pipefy-automations](automations/pipefy-automations/SKILL.md) | Traditional and AI automations, simulation. 15 MCP tools. |
| **AI Agents** | [pipefy-ai-agents](ai-agents/pipefy-ai-agents/SKILL.md) | Conversational AI agents and behaviors. 7 MCP tools. |
| **Observability** | [pipefy-observability](observability/pipefy-observability/SKILL.md) | Logs, usage, credits, job exports. 10 MCP tools. |
| **Members, Email & Webhooks** | [pipefy-members-email-webhooks](members-email-webhooks/pipefy-members-email-webhooks/SKILL.md) | Membership, email, webhooks. 11 MCP tools. |
| **Introspection** | [pipefy-introspection](introspection/pipefy-introspection/SKILL.md) | Schema discovery and GraphQL fallback. 6 MCP tools. |
| **Process Design** | [pipefy-process-design](process-design/pipefy-process-design/SKILL.md) | Process architecture (consulting; not execution). |
| **Process Intelligence** | [pipefy-process-intelligence](process-intelligence/pipefy-process-intelligence/SKILL.md) | Analyze pipes for improvement opportunities. |
| **API Fallback** | [pipefy-api-fallback](api-troubleshoot/pipefy-api-fallback/SKILL.md) | Raw GraphQL fallback when higher-level tools are insufficient. |

---

## Contributing

- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — frontmatter, CI checks, style, review rubric.
- [`AGENTS.md`](AGENTS.md) — authoring guide and `SKILL.md` template.
