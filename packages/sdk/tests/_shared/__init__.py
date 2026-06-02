"""Shared fixtures and payloads consumed by both SDK and MCP test suites.

Resolved via ``pythonpath`` entries (``packages/sdk/tests``) in the root
``pyproject.toml`` and ``packages/mcp/pyproject.toml`` so both
``cd packages/mcp && uv run pytest`` and ``uv run pytest`` from the workspace
root see ``_shared`` as a top-level package (SDK, MCP, and CLI test suites).
"""
