"""Tests for shared Pipefy service types and helpers."""

from typing import cast

import pytest

from pipefy_mcp.services.pipefy.types import CardSearch, copy_card_search


@pytest.mark.unit
def test_copy_card_search_preserves_defined_keys():
    src: CardSearch = {"title": "x", "include_done": True}
    assert copy_card_search(src) == {"title": "x", "include_done": True}


@pytest.mark.unit
def test_copy_card_search_strips_keys_not_on_card_search():
    """Unknown keys (e.g. from a loose MCP payload) must not reach the client."""
    loose = {"title": "x", "not_a_card_search_field": 99, "assignee_ids": ["1"]}
    out = copy_card_search(cast(CardSearch, loose))
    assert out == {"title": "x", "assignee_ids": ["1"]}
    assert "not_a_card_search_field" not in out
