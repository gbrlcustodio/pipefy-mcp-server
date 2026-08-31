# Decision records

These are the decision records behind the toolkit design: how the SDK, MCP server, and CLI are layered, how their contracts are shaped, and how the code is structured. Each record holds one decision with its context and reasoning. A record becomes immutable once it is adopted.

There are four records, one per principle. Today all four are proposed. None is adopted yet. The rule each decision produces lives in a living doc, and that is what a contributor follows day to day. A record can defer part of its decision, and its row names the deferred part. The record keeps the why. To change an adopted decision, add a new record that supersedes the old one. Do not edit an adopted record. See [`authoring.md`](../authoring.md).

| ADR | Decision | Status | Current rule |
|---|---|---|---|
| [0001](0001-layered-responsibility.md) | Layered responsibility | proposed | [`architecture.md`](../architecture.md) |
| [0002](0002-typed-single-form-contract.md) | Typed, single-form contract | proposed, typed-output rollout later | [`conventions.md`](../conventions.md) |
| [0003](0003-mcp-tools-express-outcomes.md) | MCP tools express outcomes | proposed, consolidation, resolver migration, and gate reshaping deferred | [`conventions.md`](../conventions.md) |
| [0004](0004-vertical-slice-structure.md) | Vertical-slice structure and naming | proposed, slice folders and the `Pipefy` rename deferred | [`architecture.md`](../architecture.md), [`conventions.md`](../conventions.md) |

The governance rule that a self-imposed constraint is a refactor candidate lives in [`conventions.md`](../conventions.md), not as a separate record.

## Rollout epics

The deferred work of these decisions is tracked in epics outside the records:

- Outcome-tool audit and consolidation (0003).
- Resolver migration for the two tools that ask for a missing input (0003).
- Destructive-gate reshaping: a declared effect on every write, and a dry run in place of the confirmation gate (0003).
- Vertical-slice refactor and the `Pipefy` root rename (0004).
- An import contract per package, so a check holds the role direction outside `packages/mcp` (0004).
- Typed-output rollout, resource by resource with Card first (0002).

The step-by-step exploration behind these decisions is in the repository history.
