"""Output backends for Typer commands."""

from __future__ import annotations

from . import json_renderer, rich_renderer

__all__ = ["json_renderer", "rich_renderer"]
