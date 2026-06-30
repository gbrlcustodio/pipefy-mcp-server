"""Unit tests for ``PipefyEndpoints`` (the SDK's refined endpoint value object)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipefy_sdk.endpoints import PipefyEndpoints

_VALID = {
    "graphql_url": "https://app.pipefy.com/graphql",
    "interfaces_graphql_url": "https://app.pipefy.com/graphql/interfaces",
    "internal_api_url": "https://app.pipefy.com/internal_api",
}


@pytest.mark.unit
def test_constructs_with_well_shaped_urls() -> None:
    endpoints = PipefyEndpoints(**_VALID)
    assert endpoints.graphql_url == _VALID["graphql_url"]
    assert endpoints.interfaces_graphql_url == _VALID["interfaces_graphql_url"]
    assert endpoints.internal_api_url == _VALID["internal_api_url"]


@pytest.mark.unit
def test_is_frozen() -> None:
    endpoints = PipefyEndpoints(**_VALID)
    with pytest.raises(ValidationError):
        endpoints.graphql_url = "https://other.example.com/graphql"


@pytest.mark.unit
@pytest.mark.parametrize("field", list(_VALID))
def test_rejects_non_url_shape(field: str) -> None:
    bad = {**_VALID, field: "not-a-url"}
    with pytest.raises(ValidationError, match="should match pattern"):
        PipefyEndpoints(**bad)


@pytest.mark.unit
@pytest.mark.parametrize("field", list(_VALID))
def test_rejects_query_or_fragment(field: str) -> None:
    bad = {**_VALID, field: f"{_VALID[field]}?a=1"}
    with pytest.raises(ValidationError, match="query string or fragment"):
        PipefyEndpoints(**bad)
