"""Console-script entry point for ``pipefy-mcp-server``.

With no flags the binary runs the local profile over stdio. ``--profile remote``
serves the default-deny remote-safe tool surface over Streamable HTTP;
``--transport`` overrides the profile's default wire. ``--help`` / ``--version``
let packaging smoke tests (and humans) introspect the binary without entering a
serve loop.
"""

from __future__ import annotations

import sys
from typing import Sequence

from pipefy_mcp import __version__
from pipefy_mcp.server import run_server

_HELP = (
    f"pipefy-mcp-server {__version__}\n"
    "\n"
    "Usage: pipefy-mcp-server [--help] [--version] [--profile {local|remote}]\n"
    "                        [--transport {stdio|http}] [--host HOST] [--port PORT]\n"
    "\n"
    "With no flags, the process runs the local profile over stdio (all tools, one\n"
    "startup credential) and is intended to be launched by an MCP client (e.g. an\n"
    "IDE extension or `uv run`).\n"
    "\n"
    "With --profile remote, it serves over Streamable HTTP and exposes only the\n"
    "default-deny remote-safe tool surface, validating an inbound bearer per\n"
    "request.\n"
    "\n"
    "Options:\n"
    "  --help                    Show this message and exit.\n"
    "  --version                 Show the installed version and exit.\n"
    "  --profile {local|remote}  Launch profile (default local).\n"
    "  --transport {stdio|http}  Transport wire (default: stdio for local, http\n"
    "                            for remote). 'remote' over stdio is rejected.\n"
    "  --host HOST               HTTP bind host (default env PIPEFY_MCP_HOST, else\n"
    "                            127.0.0.1).\n"
    "  --port PORT               HTTP bind port (default env PIPEFY_MCP_PORT, else\n"
    "                            8000).\n"
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


def _validate_choice(
    value: str | None, flag: str, allowed: frozenset[str]
) -> str | None:
    """Return ``value`` if it is ``None`` or an allowed label, else exit 2.

    ``None`` (flag absent) passes through so the settings layer fills the default.
    An unknown value exits with a usage error rather than surfacing a pydantic
    ``ValidationError`` later.
    """
    if value is not None and value not in allowed:
        options = "|".join(sorted(allowed))
        sys.stderr.write(f"error: {flag} must be one of {{{options}}}, got {value!r}\n")
        raise SystemExit(2)
    return value


def _parse_port(value: str | None) -> int | None:
    """Parse a ``--port`` value, exiting with a usage error on a non-integer.

    ``None`` (flag absent) passes through so ``run_server`` falls back to
    ``PIPEFY_MCP_PORT``. A non-numeric value (e.g. ``--port abc`` or ``--port ""``)
    exits 2 rather than crashing with an unhandled ``ValueError``.
    """
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        sys.stderr.write(f"error: --port must be an integer, got {value!r}\n")
        raise SystemExit(2) from None


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point declared in ``packages/mcp/pyproject.toml``."""
    args = sys.argv[1:] if argv is None else list(argv)
    if any(a in {"-h", "--help"} for a in args):
        sys.stdout.write(_HELP)
        return
    if any(a == "--version" for a in args):
        sys.stdout.write(f"{__version__}\n")
        return

    profile = _validate_choice(
        _option_value(args, "--profile"), "--profile", frozenset({"local", "remote"})
    )
    transport = _validate_choice(
        _option_value(args, "--transport"),
        "--transport",
        frozenset({"stdio", "http"}),
    )
    if profile == "remote" and transport == "stdio":
        sys.stderr.write(
            "error: the 'remote' profile requires --transport http "
            "(a per-request bearer has no stdio equivalent)\n"
        )
        raise SystemExit(2)

    host = _option_value(args, "--host")
    if host is not None and not host.strip():
        sys.stderr.write("error: --host must not be empty\n")
        raise SystemExit(2)

    # Unset flags pass through as None; run_server resolves them against
    # PIPEFY_MCP_* (and the profile-derived transport default).
    run_server(
        profile=profile,
        transport=transport,
        host=host,
        port=_parse_port(_option_value(args, "--port")),
    )


if __name__ == "__main__":
    main()
