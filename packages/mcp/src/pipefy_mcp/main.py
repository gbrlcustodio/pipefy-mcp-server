"""Console-script entry point for ``pipefy-mcp-server``.

The server itself talks MCP over stdio with no flags, but the binary accepts
``--help`` / ``--version`` so packaging smoke tests (and humans) can introspect
it without entering the stdio loop. Any other argv runs the server as before.
"""

from __future__ import annotations

import sys
from typing import Sequence

from pipefy_mcp import __version__
from pipefy_mcp.server import run_server

_HELP = (
    f"pipefy-mcp-server {__version__}\n"
    "\n"
    "Usage: pipefy-mcp-server [--help] [--version]\n"
    "\n"
    "Runs the Pipefy MCP server over stdio. With no flags, the process speaks\n"
    "the Model Context Protocol on stdin/stdout and is intended to be launched\n"
    "by an MCP client (e.g. an IDE extension or `uv run`).\n"
    "\n"
    "Options:\n"
    "  --help     Show this message and exit.\n"
    "  --version  Show the installed version and exit.\n"
)


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point declared in ``packages/mcp/pyproject.toml``."""
    args = sys.argv[1:] if argv is None else list(argv)
    if any(a in {"-h", "--help"} for a in args):
        sys.stdout.write(_HELP)
        return
    if any(a == "--version" for a in args):
        sys.stdout.write(f"{__version__}\n")
        return

    run_server()


if __name__ == "__main__":
    main()
