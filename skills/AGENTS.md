# Skills — Authoring Guide

This document defines how to author, name, and maintain skills in the `pipefy-labs` monorepo.

---

## What is a skill?

A skill is a single Markdown file (`SKILL.md`) with YAML frontmatter and a structured body describing a Pipefy workflow. Any LLM agent (Claude Code, Cursor, Codex, custom) can read the file and execute the described steps using the MCP server or CLI.

---

## Directory structure

```
skills/
  <domain>/
    <skill-name>/
      SKILL.md          ← the skill file
  AGENTS.md             ← this file
  README.md             ← catalog index
```

**Domain folders** match the MCP tool surface:
`pipes-and-cards`, `database-tables`, `relations`, `reports`, `automations`, `ipaas`, `ai-agents`, `observability`, `members-email-webhooks`, `portal-setup`, `attachments`, `introspection`, `building`, `process-design`, `process-intelligence`, `api-troubleshoot`, `onboarding`

---

## SKILL.md template

```markdown
---
name: pipefy-<domain>-<action>   # kebab-case, unique
description: >
  One-line summary used by agents to choose this skill.
  Be specific about when to use vs not use.
tags: [pipefy, <domain>, ...]
---

# Title

Short intro (1-2 sentences). State the tool count when relevant.

---

## When to use

The user intent that triggers this skill (examples). State when NOT to use this skill.

## Prerequisites

What must be true before the agent can execute (IDs, access, config).

## Tools needed

| Tool (MCP) | CLI equivalent | Read-only |
|------------|----------------|-----------|
| `tool_name` | `pipefy domain action` | Yes/No |

## Steps

1. **Step name** — description.

   MCP:
   ```
   tool_name arg1=value1 arg2=value2
   ```

   CLI:
   ```bash
   pipefy domain action --flag value
   ```

2. **Next step** — ...

## Success criteria

How the agent / human knows the workflow completed correctly.

## Failure modes

Common errors and how to recover.
```

---

## Naming conventions

- **Skill names:** kebab-case, descriptive, start with `pipefy-` (`pipefy-pipes-and-cards`, `pipefy-process-design`).
- **Domain folders:** kebab-case, plural where natural (`pipes-and-cards`, `automations`).
- **Stable IDs:** once a skill is published, renames require a CHANGELOG note so agent prompts using old names still resolve.

---

## Frontmatter rules

All fields are **required** unless noted:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Must match the directory name exactly. |
| `description` | Yes | One-line summary; used by agents to select this skill. |
| `tags` | No | Optional list of relevant keywords. |

CI (`skills-lint.yml`) validates these on every PR.

---

## Body style

- **Action-first headlines.** "Create a pipe" not "Pipe creation."
- **Code blocks for every invocation.** Show both MCP and CLI variants when both exist.
- **Prefer explicit IDs over names** in examples — Pipefy IDs are stable; names change.
- **Under 500 lines.** Keep skills focused; use "See also" links to related skills rather than duplicating content.
- **Progressive disclosure.** Put the common happy path first; edge cases and failure modes last.

---

## Linking to repository docs

When a skill needs stable URLs into this repo’s Markdown:

- **MCP tool semantics** — `docs/mcp/tools/<domain>.md` (cross-cutting rules: `docs/mcp/tools/cross-cutting.md`).
- **CLI-only flows** — `docs/cli/` (e.g. `docs/cli/self-healing.md`).
- **SDK usage** — `docs/sdk/README.md`.
- **Install** — always root `README.md#installation` (canonical snippets); first-time agent checklist — `skills/onboarding/pipefy-toolkit-setup/SKILL.md`; **`PIPEFY_*` env vars and `config.toml`** — `docs/config.md`; **MCP ↔ CLI matrix** — `docs/parity.md`.

---

## Intra-repo coupling

Skills and tools live in the same monorepo. When a CLI command or MCP tool is renamed:

1. Update the skill reference in the same PR (or a paired PR opened in the same review window).
2. The `skills-lint.yml` CI job validates frontmatter on every `skills/**/SKILL.md`
   and lints MCP tool names + `pipefy` CLI references in each file. A rename that
   doesn't update the skill fails the build.

---

## Best practices

- **Keep skills short.** If a skill exceeds 500 lines, split it by sub-domain.
- **Link, don't duplicate.** Reference related skills with `See also: skills/...`.
- **Test before shipping.** Run the skill end-to-end against a real Pipefy org before opening a PR.
