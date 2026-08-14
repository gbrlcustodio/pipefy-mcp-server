# Documentation authoring

This guide describes the target structure for the `docs/` tree and where a new doc goes. Its siblings are [`architecture.md`](architecture.md) and [`conventions.md`](conventions.md).

The tree is mid-migration to this target. Where a file still sits in the wrong place, an open issue tracks the move.

## Where a doc goes

Sort by audience first, then by kind.

- Contributor docs live under `docs/contributing/`.
- Consumer docs live by application under `docs/mcp/`, `docs/cli/`, and `docs/sdk/`.
- A durable, cross-cutting consumer doc lives at the `docs/` root. A fast-changing one is generated instead (see below).

Then keep a doc to one kind where practical. The Diataxis kinds are tutorial, how-to, reference, and explanation. A file that mixes several is a split candidate.

## Decision records

A decision record is contributor explanation of a distinct kind: one architectural decision, immutable once adopted. The set lives under `docs/contributing/adr/`, one file per decision. To change a decision, add a record that supersedes the old one. Do not edit an adopted record. The rule a record produces graduates to `architecture.md` or `conventions.md`, where a contributor reads the current rule. The record keeps the reasoning.

## Authoring a convention

[`conventions.md`](conventions.md) is a rule reference, and every rule takes the same form:

- A permanent ID, such as `PARSE-3`. A retired rule keeps its ID, so a citation never changes meaning.
- One rule line, which states the commitment.
- A `Do` list and a `Do not` list.
- A `Why` line, capped at three sentences.
- An optional `Weighed` line, which names the alternative that was rejected.

The `Why` line exists so that a later reader can tell when the reason stopped holding. It is part of the rule entry, so a rule reference stays one kind of document.

A new rule earns its place by correcting something that happened. A rule written against a hypothetical costs every reader and catches nobody.

A code example names no shipped symbol. A symbol in an example rots on the next refactor. A reader who greps a name that no longer exists stops trusting the whole document.

## Where a gap is documented

`conventions.md` states what we commit to, and it names no gap. A convention governs the next change, so older code that predates it is legacy rather than a shortfall.

[`architecture.md`](architecture.md) is a map rather than a rule set, so it works the other way. A map claim is either true of the code or not, and the document owes the reader every place the code is behind it. Those places gather in one final section, `Known gaps`, and each entry names the artifact that closes it. A disabled import-linter contract is one such artifact, because it sits beside the live contracts and one edit enables it. This split follows the arc42 template, which keeps the building block view apart from risks and technical debt.

Neither document carries the inventory or the remediation plan for a gap. A concrete step is closeable work, so it belongs in an issue.

## Point at the owner of a fact

Every fact has one owner: the code, a schema, an enforced contract, or another document. A document that restates a fact it does not own holds a copy, and that copy drifts. A reader then cannot tell which copy is current, so name the owner and point there. [`architecture.md`](architecture.md) names the import-linter contract rather than listing the layer modules, and it names the GraphQL schema rather than describing entity shape.

Where the code owns a list, generate the document from that code: docstrings, pydantic `Field(description=...)`, the tool registry, or Typer help. Hand-author only where there is no code source, such as a concept doc. Do not keep a generated table and durable prose in the same file.

## Keep it small

Keep recognizable names: `README`, `CHANGELOG`, `CONTRIBUTING`, `SECURITY`, `MIGRATION`, `DEPRECATION`, and `ARCHITECTURE` (as `docs/contributing/architecture.md`). A directory earns its keep by file count and homogeneity, so do not invent a `guides/` or `reference/` bucket for a few files. A concrete cleanup or migration step is a closeable task, so open an issue instead of listing it here.
