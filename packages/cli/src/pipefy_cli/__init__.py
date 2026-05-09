"""Typer CLI entry surface for Pipefy (pipefy-ai-sdk)."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pipefy-cli")
except PackageNotFoundError:
    __version__ = "0.1.0"

__all__ = ["__version__"]
