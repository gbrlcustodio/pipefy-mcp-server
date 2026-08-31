# ADR-0004: Vertical-slice structure and naming

Status: proposed, deferred to its own initiative
Date: 2026-07-20

## Context

Every package is organized horizontally, and each one sits at a different point on the same problem.

The SDK splits into `services/`, `models/`, and `queries/`, and a crowd of cross-cutting modules sits homeless at the package root. Some of those root modules take a `PipefyClient` and orchestrate calls against it, so a use case sits above the facade that it imports. The primitive layer is named `services/` although it holds only wire wrappers, so the name misdescribes it.

The MCP server splits by layer, and its import-linter contract names them: `server`, `tools`, `core`, `auth`, and `settings`. Its `tools` layer already cuts the facade from the use case across part of its surface, because a tool module can carry a `_tool_helpers.py` partner, although many tool modules carry none.

The CLI splits into `commands/` and `output/`, and it cuts nothing inside a command module. A resource module holds the Typer surface and the orchestration it drives, so the largest command modules grow without a seam.

A horizontal split tells a reader what kind of file each module is, not what the package is about.

## Decision

Organize each package by domain vertical slice, not by technical layer. The horizontal split is only the boundary between the SDK, the MCP server, and the CLI. Within a package the top level names the domain (`members/`, `pipes/`).

The domain-type, primitive, use-case, and facade distinction is a dependency contract, not a folder axis. The four are roles inside a slice (`models.py`, `client.py`, `usecases.py`, `facade.py`), held by an import-linter contract that keeps `models.py` free of transport and framework and points imports from facade to use case to client to model. Name on merits in Pipefy vocabulary, borrowing only the narrow DDD terms that cut something: anti-corruption layer, application service, domain service, and entity versus value object. The SDK exposes a facade per domain under a thin `Pipefy` composition root, which frees the name `client` for the primitive layer.

## Consequences

This is the largest bet. It spans three packages and changes the SDK public surface, including a `PipefyClient` to `Pipefy` rename that touches hundreds of references. It is deferred to its own initiative. The service-by-service split work-list is tracked in that rollout epic.

No living doc carries a rule from this decision while it stays deferred. [`architecture.md`](../architecture.md) maps the structure that holds today, which is the horizontal one. This record is the only place that describes the target.

## Target slices

The slice names are the sub-domains of Pipefy's own domain model, which is maintained outside this repository, and not names chosen here. A slice boundary therefore follows a boundary that the business already draws. The two cross-cutting exclusions below come from the same model. Its tenth sub-domain, Electronic Signature, has no tool in this repository.

Each of the three packages divides into these vertical slices:

- Work Execution
- Process Modeling
- Business Records
- Request Intake
- Identity and Access Management
- Governance and Audit
- Performance and Oversight
- Billing
- System Integration

Two capabilities stay cross-cutting, not slices: Communication (email) and the Identity facet (`packages/auth`).

Two groupings exist today, and neither one is this target. `DOMAINS` in `packages/mcp/src/pipefy_mcp/tools/toolsets.py` partitions the tool surface by feature area, and it drives the `--toolsets` flag and the `PIPEFY_MCP_TOOLSETS` variable. The CLI groups its commands per resource. Whether either grouping moves to the slice names is a question that [`architecture.md`](../architecture.md) carries under `Known gaps`, because a rename there breaks a published vocabulary.
