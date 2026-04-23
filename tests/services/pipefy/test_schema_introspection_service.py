"""Unit tests for SchemaIntrospectionService."""

from unittest.mock import AsyncMock

import pytest
from gql.transport.exceptions import TransportQueryError
from graphql import GraphQLError

from pipefy_mcp.services.pipefy.queries.introspection_queries import (
    INTROSPECT_MUTATION_QUERY,
    INTROSPECT_QUERY_QUERY,
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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_introspect_query_returns_name_args_and_return_type(mock_settings):
    """Inspecting a valid query returns name, description, args, and return type."""
    fields = [
        {
            "name": "me",
            "description": "Current user",
            "args": [],
            "type": {"name": "User", "kind": "OBJECT"},
        },
        {
            "name": "pipe",
            "description": "Lookup a pipe by its ID",
            "args": [
                {
                    "name": "id",
                    "type": {
                        "name": None,
                        "kind": "NON_NULL",
                        "ofType": {"name": "ID", "kind": "SCALAR"},
                    },
                    "defaultValue": None,
                }
            ],
            "type": {"name": "Pipe", "kind": "OBJECT"},
        },
    ]
    service = _make_service(mock_settings, {"__type": {"fields": fields}})
    result = await service.introspect_query("pipe")

    service.execute_query.assert_called_once()
    query_used, variables = service.execute_query.call_args[0]
    assert query_used is INTROSPECT_QUERY_QUERY
    assert variables == {}
    assert "error" not in result
    assert result["name"] == "pipe"
    assert result["description"] == "Lookup a pipe by its ID"
    assert len(result["args"]) == 1
    assert result["args"][0]["name"] == "id"
    assert result["type"]["name"] == "Pipe"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_introspect_query_not_found_returns_clear_error(mock_settings):
    """When the query name is not on the Query type, return a clear error."""
    fields = [
        {
            "name": "me",
            "description": None,
            "args": [],
            "type": {"name": "User", "kind": "OBJECT"},
        }
    ]
    service = _make_service(mock_settings, {"__type": {"fields": fields}})
    result = await service.introspect_query("nonexistent")

    assert "error" in result
    assert "not found" in result["error"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_introspect_query_root_type_none_returns_clear_error(mock_settings):
    """When __type itself is None (Query root not found), return a clear error."""
    service = _make_service(mock_settings, {"__type": None})
    result = await service.introspect_query("pipe")

    assert "error" in result
    assert "query" in result["error"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_introspect_type_default_depth_is_1_no_recursive_resolution(
    mock_settings,
):
    """Default max_depth=1 returns as-is without resolving referenced types."""
    gql_type = {
        "name": "Card",
        "kind": "OBJECT",
        "description": "A card",
        "fields": [
            {
                "name": "assignees",
                "description": None,
                "type": {"name": "User", "kind": "OBJECT", "ofType": None},
            }
        ],
        "inputFields": None,
        "enumValues": None,
    }
    service = _make_service(mock_settings, {"__type": gql_type})
    result = await service.introspect_type("Card")

    service.execute_query.assert_called_once()
    assert "resolvedType" not in result["fields"][0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_introspect_type_depth_2_resolves_deeply_wrapped_types(mock_settings):
    """max_depth=2 resolves types wrapped in NON_NULL(LIST(NON_NULL(...)))."""
    card_type = {
        "name": "Card",
        "kind": "OBJECT",
        "description": "A card",
        "fields": [
            {
                "name": "assignees",
                "description": None,
                "type": {
                    "name": None,
                    "kind": "NON_NULL",
                    "ofType": {
                        "name": None,
                        "kind": "LIST",
                        "ofType": {"name": "User", "kind": "OBJECT"},
                    },
                },
            },
        ],
        "inputFields": None,
        "enumValues": None,
    }
    user_type = {
        "name": "User",
        "kind": "OBJECT",
        "description": "A user",
        "fields": [
            {
                "name": "name",
                "description": None,
                "type": {"name": "String", "kind": "SCALAR", "ofType": None},
            }
        ],
        "inputFields": None,
        "enumValues": None,
    }

    service = SchemaIntrospectionService(settings=mock_settings)

    async def mock_execute_query(query, variables):
        type_name = variables.get("typeName", "")
        if type_name == "User":
            return {"__type": user_type}
        return {"__type": card_type}

    service.execute_query = AsyncMock(side_effect=mock_execute_query)
    result = await service.introspect_type("Card", max_depth=2)

    assignees_field = result["fields"][0]
    assert "resolvedType" in assignees_field
    assert assignees_field["resolvedType"]["name"] == "User"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_introspect_type_depth_2_resolves_field_types(mock_settings):
    """max_depth=2 resolves one level of referenced types."""
    card_type = {
        "name": "Card",
        "kind": "OBJECT",
        "description": "A card",
        "fields": [
            {
                "name": "assignees",
                "description": None,
                "type": {"name": "User", "kind": "OBJECT", "ofType": None},
            },
            {
                "name": "id",
                "description": None,
                "type": {"name": "ID", "kind": "SCALAR", "ofType": None},
            },
        ],
        "inputFields": None,
        "enumValues": None,
    }
    user_type = {
        "name": "User",
        "kind": "OBJECT",
        "description": "A user",
        "fields": [
            {
                "name": "name",
                "description": None,
                "type": {"name": "String", "kind": "SCALAR", "ofType": None},
            }
        ],
        "inputFields": None,
        "enumValues": None,
    }

    service = SchemaIntrospectionService(settings=mock_settings)
    call_count = 0

    async def mock_execute_query(query, variables):
        nonlocal call_count
        call_count += 1
        type_name = variables.get("typeName", "")
        if type_name == "User":
            return {"__type": user_type}
        return {"__type": card_type}

    service.execute_query = AsyncMock(side_effect=mock_execute_query)
    result = await service.introspect_type("Card", max_depth=2)

    assert call_count >= 2
    assignees_field = result["fields"][0]
    assert assignees_field["name"] == "assignees"
    assert "resolvedType" in assignees_field
    assert assignees_field["resolvedType"]["name"] == "User"
    # Scalar fields should NOT have resolvedType
    id_field = result["fields"][1]
    assert "resolvedType" not in id_field


@pytest.mark.unit
@pytest.mark.asyncio
async def test_introspect_type_depth_1_explicit_same_as_default(mock_settings):
    """Explicitly passing max_depth=1 behaves the same as default."""
    gql_type = {
        "name": "Card",
        "kind": "OBJECT",
        "description": "A card",
        "fields": [
            {
                "name": "assignees",
                "description": None,
                "type": {"name": "User", "kind": "OBJECT", "ofType": None},
            }
        ],
        "inputFields": None,
        "enumValues": None,
    }
    service = _make_service(mock_settings, {"__type": gql_type})
    result = await service.introspect_type("Card", max_depth=1)

    service.execute_query.assert_called_once()
    assert "resolvedType" not in result["fields"][0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_introspect_mutation_depth_2_resolves_arg_types(mock_settings):
    """max_depth=2 on introspect_mutation resolves argument input types."""
    mutation_fields = [
        {
            "name": "createCard",
            "description": "Create a card",
            "args": [
                {
                    "name": "input",
                    "type": {
                        "name": "CreateCardInput",
                        "kind": "INPUT_OBJECT",
                        "ofType": None,
                    },
                    "defaultValue": None,
                }
            ],
            "type": {"name": "CardPayload", "kind": "OBJECT"},
        }
    ]
    input_type = {
        "name": "CreateCardInput",
        "kind": "INPUT_OBJECT",
        "description": "Input for creating a card",
        "fields": None,
        "inputFields": [
            {
                "name": "pipe_id",
                "description": None,
                "type": {"name": "ID", "kind": "SCALAR", "ofType": None},
            }
        ],
        "enumValues": None,
    }

    service = SchemaIntrospectionService(settings=mock_settings)

    async def mock_execute_query(query, variables):
        type_name = variables.get("typeName", "")
        if type_name == "CreateCardInput":
            return {"__type": input_type}
        return {"__type": {"fields": mutation_fields}}

    service.execute_query = AsyncMock(side_effect=mock_execute_query)
    result = await service.introspect_mutation("createCard", max_depth=2)

    assert result["name"] == "createCard"
    arg = result["args"][0]
    assert "resolvedType" in arg
    assert arg["resolvedType"]["name"] == "CreateCardInput"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_introspect_query_depth_2_resolves_arg_types(mock_settings):
    """max_depth=2 on introspect_query resolves argument types."""
    query_fields = [
        {
            "name": "pipe",
            "description": "Lookup a pipe",
            "args": [
                {
                    "name": "id",
                    "type": {"name": "ID", "kind": "SCALAR", "ofType": None},
                    "defaultValue": None,
                }
            ],
            "type": {"name": "Pipe", "kind": "OBJECT"},
        }
    ]

    service = _make_service(mock_settings, {"__type": {"fields": query_fields}})
    result = await service.introspect_query("pipe", max_depth=2)

    # Scalar args should not be resolved
    assert result["name"] == "pipe"
    assert "resolvedType" not in result["args"][0]


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
async def test_search_schema_with_kind_filter_returns_only_matching_kind(mock_settings):
    """When kind is given, only types of that kind are returned."""
    types_list = [
        {"name": "CardStatus", "kind": "ENUM", "description": "Card status values"},
        {"name": "Card", "kind": "OBJECT", "description": "A card in Pipefy"},
        {"name": "CardInput", "kind": "INPUT_OBJECT", "description": "Card input"},
    ]
    service = _make_service(mock_settings, _schema_types_response(types_list))
    result = await service.search_schema("card", kind="ENUM")

    assert len(result["types"]) == 1
    assert result["types"][0]["name"] == "CardStatus"
    assert result["types"][0]["kind"] == "ENUM"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_schema_kind_none_returns_all_matching(mock_settings):
    """When kind is None (default), all matching types are returned regardless of kind."""
    types_list = [
        {"name": "CardStatus", "kind": "ENUM", "description": "Card status values"},
        {"name": "Card", "kind": "OBJECT", "description": "A card in Pipefy"},
        {"name": "CardInput", "kind": "INPUT_OBJECT", "description": "Card input"},
    ]
    service = _make_service(mock_settings, _schema_types_response(types_list))
    result = await service.search_schema("card", kind=None)

    assert len(result["types"]) == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_schema_kind_no_matches_returns_empty(mock_settings):
    """When kind filter excludes all keyword matches, return empty list."""
    types_list = [
        {"name": "Card", "kind": "OBJECT", "description": "A card"},
    ]
    service = _make_service(mock_settings, _schema_types_response(types_list))
    result = await service.search_schema("card", kind="UNION")

    assert result["types"] == []


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
async def test_execute_graphql_query_field_not_found_hints_mutation(mock_settings):
    """When a field doesn't exist on Query but exists on Mutation, add a hint."""
    call_count = 0

    async def mock_execute(query, variables):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise TransportQueryError(
                "GraphQL Error",
                errors=[
                    {"message": "Cannot query field 'createCard' on type 'Query'."}
                ],
            )
        # Hint lookup: return Mutation fields that include createCard
        return {
            "__type": {
                "fields": [
                    {"name": "createCard", "description": "Create a card"},
                    {"name": "updateCard", "description": "Update a card"},
                ]
            }
        }

    service = SchemaIntrospectionService(settings=mock_settings)
    service.execute_query = AsyncMock(side_effect=mock_execute)
    result = await service.execute_graphql("query Q { createCard { id } }", None)

    assert "errors" in result
    err = result["errors"][0]
    assert "hint" in err
    assert "mutation" in err["hint"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_graphql_mutation_field_not_found_hints_query(mock_settings):
    """When a field doesn't exist on Mutation but exists on Query, add a hint."""
    call_count = 0

    async def mock_execute(query, variables):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise TransportQueryError(
                "GraphQL Error",
                errors=[{"message": "Cannot query field 'pipe' on type 'Mutation'."}],
            )
        return {
            "__type": {
                "fields": [
                    {"name": "pipe", "description": "Lookup a pipe"},
                ]
            }
        }

    service = SchemaIntrospectionService(settings=mock_settings)
    service.execute_query = AsyncMock(side_effect=mock_execute)
    result = await service.execute_graphql("mutation M { pipe(id: 1) { name } }", None)

    assert "errors" in result
    err = result["errors"][0]
    assert "hint" in err
    assert "query" in err["hint"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_graphql_no_hint_when_field_absent_from_both(mock_settings):
    """When the field doesn't exist on either root type, no hint is added."""
    call_count = 0

    async def mock_execute(query, variables):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise TransportQueryError(
                "GraphQL Error",
                errors=[
                    {"message": "Cannot query field 'nonexistent' on type 'Query'."}
                ],
            )
        return {"__type": {"fields": [{"name": "pipe"}]}}

    service = SchemaIntrospectionService(settings=mock_settings)
    service.execute_query = AsyncMock(side_effect=mock_execute)
    result = await service.execute_graphql("query Q { nonexistent }", None)

    assert "errors" in result
    assert "hint" not in result["errors"][0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_graphql_hint_works_with_backtick_error_format(mock_settings):
    """Hint detection works when Pipefy uses backticks in error messages."""
    call_count = 0

    async def mock_execute(query, variables):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise TransportQueryError(
                "GraphQL Error",
                errors=[
                    {"message": "Cannot query field `createCard` on type `Query`."}
                ],
            )
        return {
            "__type": {
                "fields": [{"name": "createCard", "description": "Create a card"}]
            }
        }

    service = SchemaIntrospectionService(settings=mock_settings)
    service.execute_query = AsyncMock(side_effect=mock_execute)
    result = await service.execute_graphql("query Q { createCard { id } }", None)

    assert "errors" in result
    err = result["errors"][0]
    assert "hint" in err
    assert "mutation" in err["hint"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_graphql_no_hint_on_unrelated_error(mock_settings):
    """Errors that don't match the field-not-found pattern get no hint."""

    async def raise_transport_error(*_args, **_kwargs):
        raise TransportQueryError(
            "GraphQL Error",
            errors=[{"message": "Permission denied"}],
        )

    service = SchemaIntrospectionService(settings=mock_settings)
    service.execute_query = AsyncMock(side_effect=raise_transport_error)
    result = await service.execute_graphql("query Q { __typename }", None)

    assert "errors" in result
    assert "hint" not in result["errors"][0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_graphql_hint_lookup_failure_does_not_mask_error(mock_settings):
    """If the hint introspection itself fails, the original error is preserved."""
    call_count = 0

    async def mock_execute(query, variables):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise TransportQueryError(
                "GraphQL Error",
                errors=[
                    {"message": "Cannot query field 'createCard' on type 'Query'."}
                ],
            )
        # Hint lookup also fails
        raise TransportQueryError("hint lookup failed", errors=[])

    service = SchemaIntrospectionService(settings=mock_settings)
    service.execute_query = AsyncMock(side_effect=mock_execute)
    result = await service.execute_graphql("query Q { createCard { id } }", None)

    assert "errors" in result
    assert (
        result["errors"][0]["message"]
        == "Cannot query field 'createCard' on type 'Query'."
    )
    assert "hint" not in result["errors"][0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_graphql_hint_lookup_unexpected_error_propagates(
    mock_settings, caplog
):
    """Non-domain failures during hint detection are logged and not swallowed."""
    call_count = 0

    async def mock_execute(query, variables):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise TransportQueryError(
                "GraphQL Error",
                errors=[
                    {"message": "Cannot query field 'createCard' on type 'Query'."}
                ],
            )
        raise RuntimeError("simulated bug during hint introspection")

    service = SchemaIntrospectionService(settings=mock_settings)
    service.execute_query = AsyncMock(side_effect=mock_execute)

    with caplog.at_level("ERROR"):
        with pytest.raises(RuntimeError, match="simulated bug"):
            await service.execute_graphql("query Q { createCard { id } }", None)

    assert any(
        "Unexpected error while detecting root type mismatch hint" in r.message
        for r in caplog.records
    )


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
