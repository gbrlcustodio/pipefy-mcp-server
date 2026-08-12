# ADR-0004: Vertical-slice structure and naming

Status: proposed, deferred to its own initiative
Date: 2026-07-20

## Context

The SDK is organized horizontally: `services/`, `models/`, and `queries/`, with about twenty homeless cross-cutting modules at the package root. The primitive layer is named `services/` although it holds only wire wrappers, so the name misdescribes it. A horizontal split tells a reader what kind of file each module is, not what the package is about.

## Decision

Organize each package by domain vertical slice, not by technical layer. The horizontal split is only the boundary between the SDK, the MCP server, and the CLI. Within a package the top level names the domain (`members/`, `pipes/`).

The domain-type, primitive, use-case, and facade distinction is a dependency contract, not a folder axis. The four are roles inside a slice (`models.py`, `client.py`, `usecases.py`, `facade.py`), held by an import-linter contract that keeps `models.py` free of transport and framework and points imports from facade to use case to client to model. Name on merits in Pipefy vocabulary, borrowing only the narrow DDD terms that cut something: anti-corruption layer, application service, domain service, and entity versus value object. The SDK exposes a facade per domain under a thin `Pipefy` composition root, which frees the name `client` for the primitive layer.

## Consequences

This is the largest bet. It spans three packages and changes the SDK public surface, including a `PipefyClient` to `Pipefy` rename that touches hundreds of references. It is deferred to its own initiative. The service-by-service split work-list is tracked in that rollout epic.

The current rule lives in [`architecture.md`](../architecture.md).

## Target slices

The SDK divides into these vertical slices:

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
