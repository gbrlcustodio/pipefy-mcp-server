"""Shared fixtures for tool tests."""

import json

import pytest


@pytest.fixture
def extract_payload():
    """Extract tool payload from CallToolResult across MCP SDK versions."""

    def _extract(result) -> dict:
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            if isinstance(structured, dict) and "result" in structured:
                payload = structured.get("result")
                if isinstance(payload, dict):
                    return payload
            if isinstance(structured, dict):
                return structured
        content = getattr(result, "content", None) or []
        for item in content:
            if getattr(item, "type", None) == "text":
                text = getattr(item, "text", "")
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    return payload
        raise AssertionError("Could not extract tool payload from CallToolResult")

    return _extract
