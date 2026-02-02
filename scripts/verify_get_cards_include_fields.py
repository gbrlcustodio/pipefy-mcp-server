#!/usr/bin/env -S uv run python
"""Manual verification script for get_cards with include_fields (task 5.2).

Calls get_cards(pipe_id, include_fields=False) and get_cards(pipe_id, include_fields=True)
via PipefyClient and prints whether card nodes include the 'fields' key when
include_fields=True.

Usage:
  From project root with .env (or PIPEFY_* env vars) and a pipe ID:
    uv run python scripts/verify_get_cards_include_fields.py <pipe_id>
  Or set PIPEFY_VERIFY_PIPE_ID and run:
    uv run python scripts/verify_get_cards_include_fields.py
"""

import asyncio
import os
import sys


def main() -> None:
    pipe_id_str = (
        sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PIPEFY_VERIFY_PIPE_ID")
    )
    if not pipe_id_str or not pipe_id_str.isdigit():
        print(
            "Usage: uv run python scripts/verify_get_cards_include_fields.py <pipe_id>",
            file=sys.stderr,
        )
        print(
            "Or set PIPEFY_VERIFY_PIPE_ID and run without arguments.",
            file=sys.stderr,
        )
        sys.exit(1)

    pipe_id = int(pipe_id_str)
    asyncio.run(_run_verification(pipe_id))


async def _run_verification(pipe_id: int) -> None:
    from pipefy_mcp.services.pipefy import PipefyClient
    from pipefy_mcp.settings import settings

    client = PipefyClient(settings=settings.pipefy)

    print(f"Pipe ID: {pipe_id}")
    print("Calling get_cards(pipe_id, search=None, include_fields=False)...")
    without_fields = await client.get_cards(pipe_id, None, include_fields=False)
    edges = without_fields.get("cards", {}).get("edges", [])
    count = len(edges)
    first_node = edges[0].get("node", {}) if edges else {}
    has_fields_key_without = "fields" in first_node
    print(f"  Cards returned: {count}")
    print(f"  First node has 'fields' key: {has_fields_key_without}")
    print()

    print("Calling get_cards(pipe_id, search=None, include_fields=True)...")
    with_fields = await client.get_cards(pipe_id, None, include_fields=True)
    edges_with = with_fields.get("cards", {}).get("edges", [])
    count_with = len(edges_with)
    first_node_with = edges_with[0].get("node", {}) if edges_with else {}
    has_fields_key_with = "fields" in first_node_with
    print(f"  Cards returned: {count_with}")
    print(f"  First node has 'fields' key: {has_fields_key_with}")
    fields_val = first_node_with.get("fields")
    if has_fields_key_with and fields_val is not None:
        sample = fields_val[:3] if isinstance(fields_val, list) else [fields_val]
        print(f"  First node 'fields' sample: {sample!r}")
    print()

    if has_fields_key_with and not has_fields_key_without:
        print("OK: include_fields=True returns nodes with 'fields'; False does not.")
    elif has_fields_key_with and has_fields_key_without:
        print("Note: Both responses have 'fields' on nodes (API may always return it).")
    elif not has_fields_key_with and count_with > 0:
        print("WARN: include_fields=True but first node has no 'fields' key.")
    else:
        print("Info: No cards in pipe or single response shape.")


if __name__ == "__main__":
    main()
