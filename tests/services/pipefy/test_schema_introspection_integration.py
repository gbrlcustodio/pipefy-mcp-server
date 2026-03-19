"""Live Pipefy GraphQL scenarios for SchemaIntrospectionService.

Requires valid Pipefy credentials (e.g. `.env` with PIPEFY_*). Skips automatically
when credentials are missing so CI stays green.

Run locally:
    uv run pytest tests/services/pipefy/test_schema_introspection_integration.py -m integration -v
"""

import pytest

from pipefy_mcp.services.pipefy.schema_introspection_service import (
    SchemaIntrospectionService,
)
from pipefy_mcp.settings import settings


def _pipefy_live_configured() -> bool:
    p = settings.pipefy
    return bool(p.graphql_url and p.oauth_url and p.oauth_client and p.oauth_secret)


@pytest.fixture
def live_svc():
    if not _pipefy_live_configured():
        pytest.skip(
            "Pipefy credentials not configured (PIPEFY_GRAPHQL_URL + OAuth in .env)"
        )
    return SchemaIntrospectionService(settings=settings.pipefy)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_agent_inspects_query_root_then_sees_many_fields(live_svc):
    """Real schema: Query is an OBJECT with a non-empty field list."""
    data = await live_svc.introspect_type("Query")
    assert "error" not in data
    assert data.get("kind") == "OBJECT"
    fields = data.get("fields") or []
    assert len(fields) >= 10
    names = {f.get("name") for f in fields if isinstance(f, dict)}
    assert "__typename" in names or "organizations" in names or "pipe" in names


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_unknown_type_returns_error_payload(live_svc):
    """Invalid type name yields a structured error (agent can retry)."""
    data = await live_svc.introspect_type("ZZZNonexistentType999Pipeclaw")
    assert "error" in data
    assert "not found" in data["error"].lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_inspect_create_card_before_hypothetical_raw_call(live_svc):
    """Scenario: introspect mutation used before building variables for execute_graphql."""
    m = await live_svc.introspect_mutation("createCard")
    assert "error" not in m
    assert m.get("name") == "createCard"
    arg_names = {a.get("name") for a in (m.get("args") or []) if isinstance(a, dict)}
    assert "input" in arg_names


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_unknown_mutation_returns_error(live_svc):
    data = await live_svc.introspect_mutation("notARealMutationPipeclaw999")
    assert "error" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_search_finds_card_types_and_excludes_double_underscore(live_svc):
    data = await live_svc.search_schema("Card")
    types = data.get("types", [])
    assert len(types) >= 1
    for t in types:
        name = t.get("name") or ""
        assert not name.startswith("__")
        assert "card" in name.lower() or (
            (t.get("description") or "").lower().find("card") >= 0
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_search_no_matches_empty_list(live_svc):
    data = await live_svc.search_schema("zzzzpipeclawnomatch99999")
    assert data.get("types") == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_execute_minimal_read_query(live_svc):
    data = await live_svc.execute_graphql("query T { __typename }", None)
    assert "error" not in data
    assert "errors" not in data
    assert data.get("__typename") == "Query"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_execute_organizations_read_scenario(live_svc):
    """Scenario: operation with no dedicated MCP tool, validated + executed."""
    data = await live_svc.execute_graphql(
        "query Orgs { organizations { id } }",
        None,
    )
    assert "error" not in data
    assert "errors" not in data
    orgs = data.get("organizations")
    assert isinstance(orgs, list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_execute_invalid_field_surfaces_errors_payload(live_svc):
    data = await live_svc.execute_graphql(
        "query Bad { thisFieldDoesNotExistOnQuery }",
        None,
    )
    assert "errors" in data
    assert any(
        "thisFieldDoesNotExistOnQuery" in (e.get("message") or "").lower()
        or "cannot query field" in (e.get("message") or "").lower()
        for e in data["errors"]
        if isinstance(e, dict)
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_execute_syntax_error_no_network_payload_shape(live_svc):
    data = await live_svc.execute_graphql("query { trailing", None)
    assert "error" in data
    err = data["error"].lower()
    assert "syntax" in err or "invalid" in err or "unexpected" in err
