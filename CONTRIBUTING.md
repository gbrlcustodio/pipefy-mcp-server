# Contributing to pipefy-labs

Thanks for helping improve the monorepo. This guide covers **skills** (Markdown playbooks). For **MCP tools, CLI commands, and SDK** work, follow [`AGENTS.md`](AGENTS.md) and the [Development](README.md#development) section in the root README (TDD, parity with [`docs/parity.md`](docs/parity.md), `ruff`, `pytest`).

---

## Contributing a skill

Skills are Markdown-only — no Python, no `uv`, no test infrastructure required. If you can write a numbered list and a YAML header, you can contribute a skill.

### Quick start

1. Fork and clone the repo.
2. Choose or create a domain folder under `skills/`.
3. Create `skills/<domain>/<skill-name>/SKILL.md` using the template in [`skills/AGENTS.md`](skills/AGENTS.md).
4. Run the reference linter locally (optional; CI runs the same check):

   ```bash
   uv run python .github/workflows/scripts/lint_skill_refs.py
   ```

5. Open a PR. CI validates frontmatter, starter-pack bundle drift, MCP tool names, and
   `pipefy` CLI subcommands referenced in each `SKILL.md`.

### Frontmatter requirements

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

### Naming rules

- **Skill folder names:** kebab-case, prefixed with `pipefy-` (e.g., `pipefy-process-design`).
- **Domain folders:** match the existing domains in `skills/`. Open an issue before creating a new domain.
- **Stable IDs:** once merged, renames need a CHANGELOG note and skill-lint allowlist update.

### Style guide

- Action-first headlines: "Create a card" not "Card creation process".
- Show MCP tool names in tables; add the CLI equivalent when it is **shipped** in [`docs/parity.md`](docs/parity.md), or mark deferred CLI as `— (deferred)`.
- Prefer explicit IDs over names (Pipefy IDs are stable; labels change).
- Keep the skill under 500 lines. Split by sub-domain if it grows larger.
- Link to related skills with `See also:` rather than copying content.

### Tool references

Every MCP tool name and top-level `pipefy` CLI token referenced in a `SKILL.md` table
or example is checked in CI (`skills-lint.yml` runs `.github/workflows/scripts/lint_skill_refs.py`):

- MCP tool names in the first column of tool tables must exist in `PIPEFY_TOOL_NAMES`.
- Invocations of the form `pipefy <subcommand>` must use a subcommand registered on the
  root CLI (see `packages/cli/src/pipefy_cli/main.py`).

If you reference a tool or CLI surface that does not exist yet, CI will fail. Either wait
for the capability to ship, or open the PR as a draft and link the implementation PR.

### Intra-repo coupling rule

If a PR renames a CLI command or MCP tool and your skill references that command, update the skill in the **same PR**. The coupling rule is enforced by CI.

### Review rubric

PRs are reviewed for:

1. Frontmatter valid and `name` matches directory.
2. Content is accurate against the current MCP/CLI surface.
3. Examples are runnable (checked manually by reviewer against a real Pipefy org for high-impact skills).
4. Style matches guide above.
5. No persona-specific content (skills are generic, not tailored to a specific agent identity).

---

## Questions

Open an issue or reach out at **dev@pipefy.com**.
