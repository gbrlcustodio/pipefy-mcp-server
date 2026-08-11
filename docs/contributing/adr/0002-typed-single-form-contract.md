# ADR-0002: Typed, single-form contract

Status: adopted for arguments and identifiers. The typed-output rollout is in progress.
Date: 2026-07-23

## Context

The SDK was a thin GraphQL passthrough. Most facade methods returned a bare `dict`, mutators accepted `**attrs: Any`, and identifiers were `str | int` pockets. Wire shape leaked into both client products: key casing, `edges`/`node` envelopes, and dict keys the caller had to know by string. The clients re-dug the same shapes and re-validated data the SDK already held. Arguments compounded the problem when one parameter accepted an id, a uuid, or a slug and sniffed which form it received.

## Decision

The SDK public contract is explicit, single-form, and typed in both directions.

An argument names exactly one form and never branches on a runtime value to guess intent. A second form is a separate named field, a `_by_*` sibling, or a caller-constructed sum type (`PipeRef = ById | ByUuid`) matched exhaustively. Identifier form is a per-surface choice: the SDK is numeric-first, the CLI takes deterministic ids with name resolution behind an opt-in flag, and the MCP server takes the human intent with an id fast-path field.

Methods return domain models named in Pipefy vocabulary, not wire dicts. Wire concerns terminate at the SDK: casing settles to one Python-idiomatic form, `edges`/`node` is dropped, and an id is carried as the `str` the GraphQL `ID` scalar promises. The wire-to-domain mapping is a `from_wire` classmethod invoked at the facade, the same seam that runs deterministic resolution. A thin per-domain wire mirror stays a pure passthrough and doubles as the uuid fast-path, added only where a caller earns it.

## Consequences

Each surface is homogeneous on its own terms, and both client products shed the dict-shuffling glue. The cost is more fields and more methods than a polymorphic argument would need. If uuid-first were ever wanted, the two-tier structure makes it a reskin, not a rewrite. The typed-output change is breaking, so it rolls out resource by resource behind the stable facade, with Card first. The resource sequence is tracked in the typed-output rollout epic.

The current rules live in [`conventions.md`](../conventions.md).
