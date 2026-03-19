"""Unit tests for SchemaIntrospectionService."""

from unittest.mock import AsyncMock

import pytest
from gql.transport.exceptions import TransportQueryError
from graphql import GraphQLError

from pipefy_mcp.services.pipefy.queries.introspection_queries import (
    INTROSPECT_MUTATION_QUERY,
    INTROSPECT_TYPE_QUERY,
    SCHEMA_TYPES_QUERY,
)
from pipefy_mcp.services.pipefy.schema_introspection_service import (
    SchemaIntrospectionService,
)
from pipefy_mcp.settings import PipefySettings


@pytest.fixture
def mock_settings():
    return PipefySettings(
        graphql_url="https://api.pipefy.com/graphql",
        oauth_url="https://auth.pipefy.com/oauth/token",
        oauth_client="client_id",
        oauth_secret="client_secret",
    )


def _make_service(mock_settings, return_value):
    service = SchemaIntrospectionService(settings=mock_settings)
    service.execute_query = AsyncMock(return_value=return_value)
    return service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_introspect_type_object_returns_fields(mock_settings):
    """Inspecting an OBJECT type returns field definitions."""
    gql_type = {
        "name": "Card",
        "kind": "OBJECT",
        "description": "A card",
        "fields": [
            {
                "name": "id",
                "description": None,
                "type": {
                    "name": None,
                    "kind": "NON_NULL",
                    "ofType": {"name": "ID", "kind": "SCALAR"},
                },
            }
        ],
        "inputFields": None,
        "enumValues": None,
    }
    service = _make_service(mock_settings, {"__type": gql_type})
    result = await service.introspect_type("Card")

    service.execute_query.assert_called_once()
    query_used, variables = service.execute_query.call_args[0]
    assert query_used is INTROSPECT_TYPE_QUERY
    assert variables == {"typeName": "Card"}
    assert result == gql_type
    assert result["fields"]
    assert result["fields"][0]["name"] == "id"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_introspect_type_input_returns_input_fields(mock_settings):
    """Inspecting an INPUT_OBJECT type returns inputFields."""
    gql_type = {
        "name": "CreateCardInput",
        "kind": "INPUT_OBJECT",
        "description": "Input to create a card",
        "fields": None,
        "inputFields": [
            {
                "name": "pipe_id",
                "description": None,
                "type": {
                    "name": None,
                    "kind": "NON_NULL",
                    "ofType": {"name": "ID", "kind": "SCALAR"},
                },
            }
        ],
        "enumValues": None,
    }
    service = _make_service(mock_settings, {"__type": gql_type})
    result = await service.introspect_type("CreateCardInput")

    assert result == gql_type
    assert result["inputFields"]
    assert result["inputFields"][0]["name"] == "pipe_id"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_introspect_type_enum_returns_enum_values(mock_settings):
    """Inspecting an ENUM type returns enumValues."""
    gql_type = {
        "name": "CardStatus",
        "kind": "ENUM",
        "description": "Status values",
        "fields": None,
        "inputFields": None,
        "enumValues": [
            {"name": "OPEN", "description": None},
            {"name": "DONE", "description": "Completed"},
        ],
    }
    service = _make_service(mock_settings, {"__type": gql_type})
    result = await service.introspect_type("CardStatus")

    assert result == gql_type
    assert result["enumValues"]
    assert {ev["name"] for ev in result["enumValues"]} == {"OPEN", "DONE"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_introspect_type_not_found_returns_clear_error(mock_settings):
    """When __type is null, return a clear error (not the raw GraphQL envelope)."""
    service = _make_service(mock_settings, {"__type": None})
    result = await service.introspect_type("NonexistentType")

    assert "error" in result
    assert (
        "nonexistenttype" in result["error"].lower()
        or "not found" in result["error"].lower()
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_introspect_mutation_returns_name_args_and_return_type(mock_settings):
    """Inspecting a valid mutation returns name, description, args, and return type."""
    fields = [
        {
            "name": "updateCard",
            "description": "Other mutation",
            "args": [],
            "type": {"name": "CardPayload", "kind": "OBJECT"},
        },
        {
            "name": "createCard",
            "description": "Create a new card",
            "args": [
                {
                    "name": "input",
                    "type": {
                        "name": None,
                        "kind": "NON_NULL",
                        "ofType": {"name": "CreateCardInput", "kind": "INPUT_OBJECT"},
                    },
                    "defaultValue": None,
                }
            ],
            "type": {"name": "CardPayload", "kind": "OBJECT"},
        },
    ]
    service = _make_service(mock_settings, {"__type": {"fields": fields}})
    result = await service.introspect_mutation("createCard")

    service.execute_query.assert_called_once()
    query_used, variables = service.execute_query.call_args[0]
    assert query_used is INTROSPECT_MUTATION_QUERY
    assert variables == {}
    assert "error" not in result
    assert result["name"] == "createCard"
    assert result["description"] == "Create a new card"
    assert len(result["args"]) == 1
    assert result["args"][0]["name"] == "input"
    assert result["type"]["name"] == "CardPayload"
    assert result["type"]["kind"] == "OBJECT"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_introspect_mutation_not_found_returns_clear_error(mock_settings):
    """When the mutation name is not on the Mutation type, return a clear error."""
    fields = [
        {
            "name": "createCard",
            "description": None,
            "args": [],
            "type": {"name": "CardPayload", "kind": "OBJECT"},
        }
    ]
    service = _make_service(mock_settings, {"__type": {"fields": fields}})
    result = await service.introspect_mutation("deleteUniverse")

    assert "error" in result
    assert (
        "deleteuniverse" in result["error"].lower()
        or "not found" in result["error"].lower()
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_introspect_mutation_root_type_none_returns_clear_error(mock_settings):
    """When __type itself is None (Mutation root not found), return a clear error."""
    service = _make_service(mock_settings, {"__type": None})
    result = await service.introspect_mutation("createCard")

    assert "error" in result
    assert "mutation" in result["error"].lower()


def _schema_types_response(types_list):
    return {"__schema": {"types": types_list}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_schema_returns_matching_types_with_name_kind_description(
    mock_settings,
):
    """Keyword search returns each match with name, kind, and description."""
    types_list = [
        {"name": "User", "kind": "OBJECT", "description": "A user"},
        {
            "name": "Pipe",
            "kind": "OBJECT",
            "description": "A pipe in Pipefy",
        },
    ]
    service = _make_service(mock_settings, _schema_types_response(types_list))
    result = await service.search_schema("pipe")

    service.execute_query.assert_called_once()
    query_used, variables = service.execute_query.call_args[0]
    assert query_used is SCHEMA_TYPES_QUERY
    assert variables == {}
    assert result["types"] == [
        {"name": "Pipe", "kind": "OBJECT", "description": "A pipe in Pipefy"},
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_schema_no_matches_returns_empty_list(mock_settings):
    """When nothing matches the keyword, types is empty."""
    types_list = [
        {"name": "User", "kind": "OBJECT", "description": None},
    ]
    service = _make_service(mock_settings, _schema_types_response(types_list))
    result = await service.search_schema("zzznomatch")

    assert result["types"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_schema_missing_root_schema_returns_empty_types(mock_settings):
    """When __schema is null, treat as empty schema and return no matches."""
    service = _make_service(mock_settings, {"__schema": None})
    result = await service.search_schema("anything")

    assert result["types"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_schema_is_case_insensitive(mock_settings):
    """Matching uses case-insensitive comparison on name and description."""
    types_list = [
        {
            "name": "Pipe",
            "kind": "OBJECT",
            "description": "Workflow container",
        },
    ]
    service = _make_service(mock_settings, _schema_types_response(types_list))
    lower = await service.search_schema("pipe")
    upper = await service.search_schema("PIPE")

    assert lower["types"] == upper["types"]
    assert len(lower["types"]) == 1
    assert lower["types"][0]["name"] == "Pipe"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_schema_excludes_introspection_types_prefixed_with_double_underscore(
    mock_settings,
):
    """Types whose name starts with __ are never returned, even if the keyword matches."""
    types_list = [
        {
            "name": "__Schema",
            "kind": "OBJECT",
            "description": "GraphQL schema introspection",
        },
        {
            "name": "SchemaExtension",
            "kind": "OBJECT",
            "description": "Custom extension",
        },
    ]
    service = _make_service(mock_settings, _schema_types_response(types_list))
    result = await service.search_schema("schema")

    names = {t["name"] for t in result["types"]}
    assert "__Schema" not in names
    assert "SchemaExtension" in names


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_graphql_valid_query_returns_data(mock_settings):
    """A syntactically valid query is executed and the data dict is returned."""
    gql_data = {"__typename": "Query"}
    service = _make_service(mock_settings, gql_data)
    query = "query ExecuteGraphqlValid { __typename }"
    result = await service.execute_graphql(query, None)

    service.execute_query.assert_called_once()
    _, variables = service.execute_query.call_args[0]
    assert variables == {}
    assert result == gql_data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_graphql_valid_mutation_returns_data(mock_settings):
    """A syntactically valid mutation runs with variables passed through."""
    gql_data = {"__typename": "Mutation"}
    service = _make_service(mock_settings, gql_data)
    mutation = "mutation ExecuteGraphqlValid($flag: Boolean) { __typename }"
    variables = {"flag": True}
    result = await service.execute_graphql(mutation, variables)

    service.execute_query.assert_called_once()
    _, vars_passed = service.execute_query.call_args[0]
    assert vars_passed == variables
    assert result == gql_data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_graphql_surfaces_graphql_errors_from_transport(mock_settings):
    """TransportQueryError from the GraphQL layer is turned into a clear errors payload."""

    async def raise_transport_error(*_args, **_kwargs):
        raise TransportQueryError(
            "GraphQL Error",
            errors=[
                {
                    "message": "Cannot query field `broken` on type `Query`.",
                    "extensions": {"code": "GRAPHQL_VALIDATION_FAILED"},
                }
            ],
        )

    service = SchemaIntrospectionService(settings=mock_settings)
    service.execute_query = AsyncMock(side_effect=raise_transport_error)
    result = await service.execute_graphql("query Q { __typename }", {})

    assert "errors" in result
    assert result["errors"][0]["message"].startswith("Cannot query field")
    assert (
        result["errors"][0].get("extensions", {}).get("code")
        == "GRAPHQL_VALIDATION_FAILED"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_graphql_surfaces_gql_client_graphql_error(mock_settings):
    """Schema validation errors from gql (before or during execute) map to an errors payload."""
    service = SchemaIntrospectionService(settings=mock_settings)
    service.execute_query = AsyncMock(
        side_effect=GraphQLError("Cannot query field `nope` on type `Query`.")
    )
    result = await service.execute_graphql("query Q { __typename }", None)

    assert "errors" in result
    assert "nope" in result["errors"][0]["message"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_graphql_syntax_error_returns_validation_error(mock_settings):
    """Malformed query strings fail before transport; return a clear validation error."""
    service = _make_service(mock_settings, {})
    result = await service.execute_graphql("query { z", None)

    service.execute_query.assert_not_called()
    assert "error" in result
    assert (
        "syntax" in result["error"].lower()
        or "invalid" in result["error"].lower()
        or "unexpected" in result["error"].lower()
    )
