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

## Authoring a section of `architecture.md`

[`architecture.md`](architecture.md) fills part of the [arc42 template](https://docs.arc42.org). Where a rule below is arc42's, it says so. The rest are ours. Two rules cover every section:

- A section that arc42 numbers takes arc42's position and arc42's name.
- A section we have nothing to say about stays absent, and never empty.

Two headings still carry an earlier name: `Known gaps` at arc42 11, and `Vocabulary` at arc42 12. Each one is a rename this review has not run yet, so neither sets a precedent.

**`Requirements overview`, arc42 1.1.** The functions the toolkit delivers, then the capabilities they act on, one line each.

- A function is the toolkit's own work. What Pipefy's API already offers is a capability instead.
- Each function carries a permanent `FR` ID, under the same rule as a convention ID above.
- Say who acts, what the act is, and what the consumer gets. Put the trigger first, where there is one.
- Never say how it works, because a mechanism changes without the function changing.
- Take every capability name, and what that name covers, from Pipefy's domain model. Never from the tool catalog or the CLI tree.
- Where the domain model leaves a question open, name the capability and settle nothing. Carry nothing that model marks as internal.
- Name no tool, no command, and no count. The code owns all three.
- If a new tool would add a bullet, the list is too detailed.

**`Quality goals`, arc42 1.2.** The three to five qualities that dominate, in priority order.

- A goal is a name, one concrete scenario, and the IDs of the `QR` rows it rests on.
- Take the name from the quality catalog at [`quality.arc42.org`](https://quality.arc42.org/), and never from the nine dimensions. A dimension covers several `QR` rows, so it can never name one goal.
- The goal name is abstract, and the scenario makes it concrete, which is why a number lives in the scenario and never in a `QR` row.
- Arc42 asks for the priority order here. The `QR` rows carry none, because a rank there would reopen where each new row slots in.

Change the order when something outside this file changes what matters:

- a business pivot, such as market reach giving way to enterprise adoption
- an incident, a metric, or a load test that exposes a quality nobody ranked
- a regulation, a privacy rule, or a certification
- a cost or headcount limit that puts operability above speed
- a deprecation or a vendor change that forces portability
- new key stakeholders, who redefine what counts as success

**`Stakeholders`, arc42 1.3.** A role, a contact, and expectations in prose.

- A party earns a row when it should know the architecture, has to be convinced of it, works with the architecture or the code, needs the documentation for its work, or decides about the system. Those are arc42's five criteria, and a party that is not a person can meet them.
- Expectations cover the architecture and its documentation, which is what arc42 asks for.
- Name no `FR` and no `QR`. A run of IDs costs every reader legibility, and it pays only a completeness check, which is a different artifact.

**`Architecture constraints`, arc42 2.** The limits every decision works inside, in two tables: technical, then organizational.

- A row is a noun phrase that names the limit, and a consequence that says what the toolkit therefore does.
- Name a limit, and never a capability. A reader finds a constraint by the word that removes freedom.
- A limit earns a row when it bounds a decision this map describes. One that binds Pipefy, a contributor, or a deployer stays off the map and lives where it is set, in [`CONTRIBUTING.md`](../../CONTRIBUTING.md) or [`TERMS.md`](../../TERMS.md).
- A cell reads on its own. Use no term the map leaves undefined, and take no referent from the neighboring cell.
- Name the applications a limit applies to, in the words `Vocabulary` fixes. A contributor on one application reads that column and stops.
- Ask whether we could remove the limit today. If we could, it is not a constraint but a gap, and `Known gaps` records it with the fix as its target.
- A link that points at an owner goes under the table, never in a cell. See [Point at the owner of a fact](#point-at-the-owner-of-a-fact).

**`Context and scope`, arc42 3.** The parties the toolkit exchanges data with, in one diagram and one table, under prose that states the domain it all acts on.

- Draw the toolkit as one box, which is what arc42 asks for. Which package reaches a partner is a level-1 fact, so `Package decomposition` draws the same partners again, and arc42 asks that the two stay consistent.
- Draw every partner. Completeness is arc42's demand here and almost nowhere else in the template. A host resource that holds or carries a credential is a partner, and so is a party that stands between an application and its consumer.
- A table beside the diagram carries what crosses each boundary and which applications reach it, which arc42 recommends. It exists because no install reaches every partner, so the box alone would overstate each one.
- An inbound arrow carries the channel a consumer arrives over. An outbound arrow carries no label, because the table holds what crosses it, and the level-1 diagram repeats every partner with no label, so the two pictures cannot come to claim different things.
- One diagram carries the business context and the technical context, which arc42 allows. Technology appears only where it marks the boundary. A deployment fact that another section owns is a pointer here, and never a second statement.
- The prose states what the toolkit acts on and who it acts as. It names no capability, because `Requirements overview` owns that list, and it names no endpoint, which is the altitude [Name no vendor behind a capability](#name-no-vendor-behind-a-capability) sets.
- The legend says what a reader cannot read off the diagram or the table, and it points at the section that owns each fact they leave out.
- Mark no risk and no quality goal on a partner, though arc42 offers both. `Quality requirements` and `Known gaps` own them, and a second copy on a diagram would drift.

**`Quality requirements`, arc42 10.** Three tables of `QR` rows, split by stimulus: normal use, a serious failure, and a change to the system or to what it depends on. Those are arc42's three scenario categories.

- A permanent ID, such as `QR-7`, under the same rule as a convention ID above.
- Its dimensions. Find the row's quality in the Q42 catalog at [`quality.arc42.org`](https://quality.arc42.org/), then copy that quality's dimensions. The nine overlap by design, so a row can carry several. Never force a row to one. Arc42 10.1 offers ISO 25010 or Q42, and we take Q42.
- The demand, in one line, in the words of the party that holds it.

**`Known gaps`, arc42 11.** See [Where a gap is documented](#where-a-gap-is-documented). Arc42 11 wants those entries ordered by priority.

## Where a gap is documented

`conventions.md` states what we commit to, and it names no gap. A convention governs the next change, so older code that predates it is legacy rather than a shortfall.

[`architecture.md`](architecture.md) is a map rather than a rule set, so it works the other way. A map claim is either true of the code or not, and the document owes the reader every place the code is behind it. Those places gather in one final section, `Known gaps`, and each entry names the target that closes it. A disabled import-linter contract is one such target, because it sits beside the live contracts and one edit enables it. This split follows [the arc42 template](#authoring-a-section-of-architecturemd), which keeps the building block view apart from risks and technical debt.

Neither document carries the inventory or the remediation plan for a gap. A concrete step is closeable work, so it belongs in an issue.

## Point at the owner of a fact

Every fact has one owner: the code, a schema, an enforced contract, or another document. A document that restates a fact it does not own holds a copy, and that copy drifts. A reader then cannot tell which copy is current, so name the owner and point there. [`architecture.md`](architecture.md) names the import-linter contract rather than listing the layer modules, and it names the GraphQL schema rather than describing entity shape.

Where the code owns a list, generate the document from that code: docstrings, pydantic `Field(description=...)`, the tool registry, or Typer help. Hand-author only where there is no code source, such as a concept doc. Do not keep a generated table and durable prose in the same file.

## Name no vendor behind a capability

A Pipefy capability can run on a third-party service. Name the capability, and never the service. A document that names it hands a reader outside Pipefy the product to probe, and the vendor can change without the capability changing.

State a limit without its mechanism. [`docs/ipaas.md`](../ipaas.md) draws the iPaaS credential flow as a short-lived, pipe-scoped credential and a session-scoped access, with no endpoint, no token shape, and no step named. That is the altitude for every document here.

## Keep it small

Keep recognizable names: `README`, `CHANGELOG`, `CONTRIBUTING`, `SECURITY`, `MIGRATION`, `DEPRECATION`, and `ARCHITECTURE` (as `docs/contributing/architecture.md`). A directory earns its keep by file count and homogeneity, so do not invent a `guides/` or `reference/` bucket for a few files. A concrete cleanup or migration step is a closeable task, so open an issue instead of listing it here.
