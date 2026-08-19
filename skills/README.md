# Pipefy skills catalog

Markdown playbooks in **Anthropic Skills** format: each file describes a Pipefy workflow (prerequisites, tools, steps, success criteria). Any agent that reads project files can use them (Cursor, Claude Code, Codex, and others).

## Using the catalog

**Install via [`skills.sh`](https://github.com/vercel-labs/skills)** (55+ agent targets — Claude Code, Cursor, Codex, OpenCode, …):

```bash
npx skills add pipefy/ai-toolkit                           # all skills
npx skills add pipefy/ai-toolkit --skill pipefy-pipes-and-cards
npx skills add pipefy/ai-toolkit -g -a claude-code -y      # CI-friendly
```

`skills.sh` reads canonical `skills/**/SKILL.md` files directly from this repo; no install or wheel needed.

**Reference from source (no install):**

```bash
git clone https://github.com/pipefy/ai-toolkit.git
# Reference paths such as skills/pipes-and-cards/pipefy-pipes-and-cards/SKILL.md
# in your IDE rules or agent context.
```

---

## Catalog

| Domain | Skill | Description |
|--------|-------|-------------|
| **Pipes & Cards** | [pipefy-pipes-and-cards](pipes-and-cards/pipefy-pipes-and-cards/SKILL.md) | Pipes, phases, cards, labels; phase inventory/moves; `create_card(phase_id=…)`. Prefer over `execute_graphql` for seeding. 40 MCP tools. |
| **Database Tables** | [pipefy-database-tables](database-tables/pipefy-database-tables/SKILL.md) | Tables, records, schema, attachments. 17 MCP tools. |
| **Relations** | [pipefy-relations](relations/pipefy-relations/SKILL.md) | Pipe and card relations. 8 MCP tools. |
| **Reports** | [pipefy-reports](reports/pipefy-reports/SKILL.md) | Pipe and organization reports, async exports. 17 MCP tools. |
| **Automations** | [pipefy-automations](automations/pipefy-automations/SKILL.md) | Traditional and AI automations, simulation. 16 MCP tools. |
| **iPaaS (Advanced Automations)** | [pipefy-ipaas](ipaas/pipefy-ipaas/SKILL.md) | Build, test, publish, and manage integration flows. 4 MCP meta-tools over a per-pipe catalog; MCP-only. |
| **AI Agents** | [pipefy-ai-agents](ai-agents/pipefy-ai-agents/SKILL.md) | Conversational AI agents and behaviors. 7 MCP tools. |
| **Observability** | [pipefy-observability](observability/pipefy-observability/SKILL.md) | Logs, usage, credits, execution metrics, job exports. 11 MCP tools. |
| **Members, Email & Webhooks** | [pipefy-members-email-webhooks](members-email-webhooks/pipefy-members-email-webhooks/SKILL.md) | Membership, email, webhooks. 12 MCP tools. |
| **Portal setup** | [pipefy-portal-setup](portal-setup/pipefy-portal-setup/SKILL.md) | Main portal, pages, elements, sub-portals (publish/unpublish). 20 MCP tools. |
| **Introspection** | [pipefy-introspection](introspection/pipefy-introspection/SKILL.md) | Schema discovery and GraphQL fallback. 6 MCP tools. |
| **Attachments** | [pipefy-attachments](attachments/pipefy-attachments/SKILL.md) | Upload files to card or table-record attachment fields. 2 MCP tools. |
| **Building** | [pipefy-building](building/pipefy-building/SKILL.md) | Thin router: map build/configure intent → domain skill. Not a delivery playbook. |
| **Process Design** | [pipefy-process-design](process-design/pipefy-process-design/SKILL.md) | Process architecture (consulting; not execution). |
| **Process Intelligence** | [pipefy-process-intelligence](process-intelligence/pipefy-process-intelligence/SKILL.md) | Analyze pipes for improvement opportunities. |
| **API Fallback** | [pipefy-api-fallback](api-troubleshoot/pipefy-api-fallback/SKILL.md) | Raw GraphQL fallback when higher-level tools are insufficient. |
| **Onboarding** | [pipefy-toolkit-setup](onboarding/pipefy-toolkit-setup/SKILL.md) | First-time install: Cursor Marketplace plugin, hosted MCP, `install.sh`, or Claude Code plugin. |

---

## Contributing

- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — frontmatter, CI checks, style, review rubric.
- [`AGENTS.md`](AGENTS.md) — authoring guide.
- [`.github/skill-template/`](../.github/skill-template/) — copyable `SKILL.md` starter for new skills (local repos or PRs here).
