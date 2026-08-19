---
name: pipefy-skill-template
description: >
  Copy this file when authoring a new Pipefy skill. Replace placeholders,
  then rename the folder so it matches the frontmatter name.
tags: [pipefy, template]
---

# [Skill title]

[One or two sentences: what this skill does and when an agent should load it.]
[Optional: MCP tool count, e.g. **N MCP tools**.]

---

## When to use

- [User intent / example phrase that should trigger this skill.]
- [Another trigger.]

Do not use this skill for:

- [Out of scope — point to another skill or approach when relevant.]

## Prerequisites

- [IDs, roles, or config that must exist first — e.g. `pipe_id`, org access.]
- [Any install path: Hosted MCP, local MCP, CLI — if it matters.]

## Tools needed

| Tool (MCP) | CLI equivalent | Read-only |
|------------|----------------|-----------|
| `[mcp_tool_name]` | `pipefy [domain] [action]` | Yes/No |

Replace bracket placeholders with real MCP tool names from the live server
(or [`docs/parity.md`](../../../docs/parity.md)) and shipped CLI commands only.
Unknown names fail CI in this repository.

## Steps

1. **[Step name]** — [what to do and why.]

   MCP:
   ```
   [mcp_tool_name] [arg]=[value]
   ```

   CLI:
   ```bash
   pipefy [domain] [action] --[flag] [value]
   ```

2. **[Next step]** — ...

## Success criteria

- [Observable outcome the agent or human can verify.]

## Failure modes

| Symptom | Likely cause | Recovery |
|---------|--------------|----------|
| [Error or bad state] | [Cause] | [Fix or fallback skill] |

## See also

- [Related skill path, e.g. `skills/pipes-and-cards/pipefy-pipes-and-cards/SKILL.md`]
