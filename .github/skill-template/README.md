# Skill template (copy me)

Starter layout for a new Pipefy skill in the Anthropic Skills format. Use it in this repo (contribution) or in your own repository (private / org playbooks).

## Quick start

1. Copy this folder:

   ```bash
   cp -R .github/skill-template/pipefy-skill-template \
     skills/<domain>/pipefy-<domain>-<action>
   ```

2. Rename placeholders in `SKILL.md` (`name`, title, tags, tools, steps).
3. Ensure frontmatter `name:` matches the **directory** name exactly.
4. Read the authoring rules: [`../../skills/AGENTS.md`](../../skills/AGENTS.md).
5. Before opening a PR here: run `uv run python .github/workflows/scripts/lint_skill_refs.py` and use `git commit -s` ([DCO](../../CONTRIBUTING.md)).

Regulated domains (`legal`, `human-resources`, `finance`, `compliance`, or decisions about natural persons) also need a filled [`COMPLIANCE.md`](../../docs/compliance/COMPLIANCE.template.md) and Legal review — see [`CONTRIBUTING.md`](../../CONTRIBUTING.md).

This starter lives outside `skills/`, so it is not part of the published catalog.
