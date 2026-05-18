# CLI documentation

Material here describes **`pipefy-cli`** (Typer): terminal workflows, flags, and patterns that are not duplicated in the MCP tool docs.

## Contents

| Path | Description |
|------|-------------|
| [`self-healing.md`](self-healing.md) | Discover GraphQL operations with `pipefy introspect`, then run `pipefy graphql exec` (mutations require `--yes`) |

## Quick conventions

- **Output:** commands default to Rich tables/text; add **`--json`** for machine-readable stdout.
- **Destructive actions:** commands that delete or mutate critical data require **`--yes`** when not using `--json`-driven automation (see each command’s `--help`).
- **Configuration:** same **`PIPEFY_*`** keys as the MCP server; see **[`../setup.md`](../setup.md)**.
- **`pipefy org get`:** pass the numeric organization id as the argument, or set optional **`PIPEFY_ORG_ID`** and omit the argument (same value you would read from `pipefy pipe list --json`).
- **`pipefy graphql exec`:** pass GraphQL variables as a JSON object via **`--vars`** (not `--variables`). Example: `--vars '{"id":"301"}'`.

Implementation entrypoint: `packages/cli/src/pipefy_cli/main.py`. Parity with MCP tools: **[`../parity.md`](../parity.md)**.
