"""Output backends for Typer commands."""

from __future__ import annotations

from .json_renderer import render as render_json
from .rich_renderer import render as render_rich

__all__ = ["render_json", "render_rich"]
