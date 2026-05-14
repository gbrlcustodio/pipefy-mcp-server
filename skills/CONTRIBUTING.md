# Contributing a Skill

Skills are Markdown-only — no Python, no `uv`, no test infrastructure required. If you can write a numbered list and a YAML header, you can contribute a skill.

## Quick start

1. Fork and clone the repo.
2. Choose or create a domain folder under `skills/`.
3. Create `skills/<domain>/<skill-name>/SKILL.md` using the template in [`AGENTS.md`](AGENTS.md).
4. Run the local lint check (optional, CI will catch it too):

   ```bash
   python scripts/lint_skills.py   # if available; otherwise rely on CI
   ```

5. Open a PR. CI will validate frontmatter and tool references.

## Frontmatter requirements

Every `SKILL.md` must have valid YAML frontmatter with:

```yaml
---
name: pipefy-<domain>-<action>   # must match the directory name
description: >
  One sentence that agents use to choose this skill.
tags: [pipefy, ...]
---
```

Missing or mismatched `name` fails CI.

## Naming rules

- **Skill folder names:** kebab-case, prefixed with `pipefy-` (e.g., `pipefy-process-design`).
- **Domain folders:** match the existing domains in `skills/`. Open an issue before creating a new domain.
- Stable IDs: once merged, renames need a CHANGELOG note and skill-lint allowlist update.

## Style guide

- Action-first headlines: "Create a card" not "Card creation process".
- Show both MCP tool name and CLI equivalent in every example.
- Prefer explicit IDs over names (Pipefy IDs are stable; labels change).
- Keep the skill under 500 lines. Split by sub-domain if it grows larger.
- Link to related skills with `See also:` rather than copying content.

## Tool references

Every tool/command reference in a skill is validated by CI:
- MCP tool names (e.g., `create_card`) are checked against `PIPEFY_TOOL_NAMES`.
- CLI commands (e.g., `pipefy card create`) are checked against `pipefy --help`.

If you reference a tool that doesn't exist yet, CI will fail. Either wait for the tool to ship, or open the PR as a draft and link the tool PR.

## Intra-repo coupling rule

If a PR renames a CLI command or MCP tool and your skill references that command, update the skill in the **same PR**. The coupling rule is enforced by CI.

## Review rubric

PRs are reviewed for:
1. Frontmatter valid and `name` matches directory.
2. Content is accurate against the current MCP/CLI surface.
3. Examples are runnable (checked manually by reviewer against a real Pipefy org for high-impact skills).
4. Style matches guide above.
5. No persona-specific content (skills are generic, not tailored to a specific agent identity).

## Questions

Open an issue or reach out at **dev@pipefy.com**.
