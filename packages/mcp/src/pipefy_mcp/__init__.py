"""Pipefy MCP Server package."""

from __future__ import annotations

import re

__version__ = "0.2.0-beta.4"
version = __version__

m = re.match(r"^(\d+)\.(\d+)\.(\d+)", __version__)
if not m:
    msg = f"__version__ must start with MAJOR.MINOR.PATCH, got {__version__!r}"
    raise ValueError(msg)
version_tuple = (int(m[1]), int(m[2]), int(m[3]))

__all__ = ["__version__", "version", "version_tuple"]
