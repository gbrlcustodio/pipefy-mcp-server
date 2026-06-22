"""Console-script entry point for ``pipefy-mcp-server``.

With no flags the binary speaks MCP over stdio (the local profile). ``--remote``
starts the hosted profile instead: Streamable HTTP plus the default-deny remote
tool allowlist. ``--help`` / ``--version`` let packaging smoke tests (and humans)
introspect the binary without entering a serve loop.
"""

from __future__ import annotations

import sys
from typing import Sequence

from pipefy_mcp import __version__
from pipefy_mcp.server import run_server

_HELP = (
    f"pipefy-mcp-server {__version__}\n"
    "\n"
    "Usage: pipefy-mcp-server [--help] [--version] [--remote] [--host HOST] [--port PORT]\n"
    "\n"
    "With no flags, the process speaks the Model Context Protocol on stdin/stdout\n"
    "(the local profile) and is intended to be launched by an MCP client (e.g. an\n"
    "IDE extension or `uv run`).\n"
    "\n"
    "With --remote, the process serves over Streamable HTTP and exposes only the\n"
    "default-deny remote-safe tool surface (the hosted profile).\n"
    "\n"
    "Options:\n"
    "  --help        Show this message and exit.\n"
    "  --version     Show the installed version and exit.\n"
    "  --remote      Serve over HTTP with the default-deny remote profile.\n"
    "  --host HOST   HTTP bind host (default env PIPEFY_MCP_HOST, else 127.0.0.1).\n"
    "  --port PORT   HTTP bind port (default env PIPEFY_MCP_PORT, else 8000).\n"
)


def _option_value(args: list[str], flag: str) -> str | None:
    """Return the value for ``--flag VALUE`` or ``--flag=VALUE`` (last wins)."""
    value: str | None = None
    prefix = f"{flag}="
    for i, arg in enumerate(args):
        if arg == flag and i + 1 < len(args):
            value = args[i + 1]
        elif arg.startswith(prefix):
            value = arg[len(prefix) :]
    return value


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point declared in ``packages/mcp/pyproject.toml``."""
    args = sys.argv[1:] if argv is None else list(argv)
    if any(a in {"-h", "--help"} for a in args):
        sys.stdout.write(_HELP)
        return
    if any(a == "--version" for a in args):
        sys.stdout.write(f"{__version__}\n")
        return

    if "--remote" in args:
        # Pass the parsed flags through as-is; run_server fills any unset value
        # from PIPEFY_MCP_HOST / PIPEFY_MCP_PORT. --remote forces the
        # default-deny remote profile alongside HTTP.
        port_arg = _option_value(args, "--port")
        run_server(
            http=True,
            host=_option_value(args, "--host"),
            port=int(port_arg) if port_arg is not None else None,
            remote_mode=True,
        )
        return

    run_server()


if __name__ == "__main__":
    main()
