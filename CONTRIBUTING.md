# Contributing to ai-toolkit

Thanks for helping improve the monorepo. This guide covers **skills** (Markdown playbooks). For **MCP tools, CLI commands, and SDK** work, follow [`AGENTS.md`](AGENTS.md) and the [Development](README.md#development) section in the root README (TDD, parity with [`docs/parity.md`](docs/parity.md), `ruff`, `pytest`).

---

## Contributing a skill

Skills are Markdown-only — no Python, no `uv`, no test infrastructure required. If you can write a numbered list and a YAML header, you can contribute a skill.

### Quick start

1. Fork and clone the repo.
2. Choose or create a domain folder under `skills/`.
3. Copy the starter skill and rename it:

   ```bash
   cp -R skills/_template/pipefy-skill-template \
     skills/<domain>/pipefy-<domain>-<action>
   ```

   Fill in [`SKILL.md`](skills/_template/pipefy-skill-template/SKILL.md) using the rules in [`skills/AGENTS.md`](skills/AGENTS.md) (and [`skills/_template/README.md`](skills/_template/README.md)).
4. Run the reference linter locally (optional; CI runs the same check):

   ```bash
   uv run python .github/workflows/scripts/lint_skill_refs.py
   ```

5. Open a PR. CI validates frontmatter, MCP tool names, and `pipefy` CLI
   subcommands referenced in each `SKILL.md`.

> **Try your skill in Claude Code before opening the PR.** Point the plugin marketplace at your local clone so your branch loads live — see [Test the Claude Code plugin from a local checkout](README.md#test-the-claude-code-plugin-from-a-local-checkout).

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
- **Product words only:** use the name the Pipefy product uses, never a new one. The domain model that settles a name is internal to Pipefy, so open an issue and ask rather than coin a term.

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

## Developer Certificate of Origin (DCO)

By contributing to this repository you certify the [Developer Certificate of Origin v1.1](https://developercertificate.org). All commits must be signed off:

```bash
git commit -s -m "feat(skills): add vendor-onboarding skill"
```

Contributions are licensed to Pipefy and to all recipients under the Apache License 2.0. Pull requests without sign-off will fail CI.

---

## Content review for regulated domains

Skills and blueprints under `skills/legal/`, `skills/human-resources/`, `skills/finance/`, `skills/compliance/` (and any domain involving decisions about natural persons) undergo **substantive review by Pipefy’s Privacy, Legal & Compliance team** before merge, in addition to the standard CI lint. Expect additional review time and possible content changes. Community-contributed skills are published as templates and do not constitute professional advice; Pipefy may decline, edit, or remove any contribution at its discretion.

Published blueprints in regulated domains must include a `COMPLIANCE.md` beside the skill (start from [`docs/compliance/COMPLIANCE.template.md`](docs/compliance/COMPLIANCE.template.md)).

---

## Questions

Open an issue or reach out at **dev@pipefy.com**.
