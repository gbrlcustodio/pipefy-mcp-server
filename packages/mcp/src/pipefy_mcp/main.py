"""Console-script entry point for ``pipefy-mcp-server``.

With no flags the binary runs the local profile over stdio. ``--profile remote``
serves the default-deny remote-safe tool surface over Streamable HTTP;
``--transport`` overrides the profile's default wire. ``--help`` / ``--version``
let packaging smoke tests (and humans) introspect the binary without entering a
serve loop.
"""

from __future__ import annotations

import argparse
from typing import Sequence

from pipefy_mcp import __version__
from pipefy_mcp.server import run_server


def _build_parser() -> argparse.ArgumentParser:
    """Build the argv parser.

    ``allow_abbrev=False`` keeps a partial flag (``--prof``) from silently
    resolving to ``--profile``. Unset flags default to ``None`` so ``run_server``
    falls back to ``PIPEFY_MCP_*`` and the profile-derived transport default
    rather than to a value invented at the argv boundary.
    """
    parser = argparse.ArgumentParser(
        prog="pipefy-mcp-server",
        description=(
            "Run the Pipefy MCP server. With no flags it speaks MCP over stdio as "
            "the local profile (all tools, one startup credential), launched by an "
            "MCP client. --profile remote serves the default-deny remote-safe "
            "surface over Streamable HTTP, validating an inbound bearer per request."
        ),
        allow_abbrev=False,
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--profile",
        choices=("local", "remote"),
        help="Launch profile (default: local).",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        help=(
            "Transport wire (default: stdio for local, http for remote). "
            "'remote' over stdio is rejected."
        ),
    )
    parser.add_argument(
        "--host",
        help="HTTP bind host (default: env PIPEFY_MCP_HOST, else 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="HTTP bind port (default: env PIPEFY_MCP_PORT, else 8000).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point declared in ``packages/mcp/pyproject.toml``.

    Unknown flags are ignored rather than rejected: the MCP transport tolerates
    extra argv that client wrappers (e.g. IDE extensions) may inject, so an
    unrecognized flag must not stop the server from starting. ``--help`` /
    ``--version`` are handled by argparse and exit before the serve loop.
    """
    parser = _build_parser()
    args, _ = parser.parse_known_args(argv)

    # A cross-field rule argparse cannot express. The settings model rejects it
    # too, but failing here keeps it a clean usage error (exit 2) at the boundary.
    if args.profile == "remote" and args.transport == "stdio":
        parser.error(
            "the 'remote' profile requires --transport http "
            "(a per-request bearer has no stdio equivalent)"
        )
    # An empty --host would reach resolve_mcp_settings as an explicit init-kwarg,
    # displacing the 127.0.0.1 default and later failing the loopback check with a
    # misleading non-loopback error. Reject it as a usage error instead.
    if args.host is not None and not args.host.strip():
        parser.error("--host must not be empty")

    run_server(
        profile=args.profile,
        transport=args.transport,
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
