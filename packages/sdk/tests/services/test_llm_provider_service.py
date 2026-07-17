"""Unit tests for LlmProviderService and the shared GraphQL problem classifier."""

from __future__ import annotations

import pytest
from _shared.mock_clients import mock_executor

from pipefy_sdk.graphql_executor import GraphQLResult
from pipefy_sdk.graphql_problem import (
    GraphQLProblemKind,
    classify_exception,
    classify_graphql_error_dicts,
)
from pipefy_sdk.services.llm_provider_service import LlmProviderService

BYOM_NODE = {
    "__typename": "LlmProvider",
    "id": "42",
    "name": "Azure custom",
    "type": "byom",
    "active": True,
    "organizationDefault": False,
    "configuration": {
        "provider": "azure_openai",
        "auth": {"accessToken": "__REDACTED__"},
    },
}

SYSTEM_NODE = {
    "__typename": "SystemLlmProvider",
    "id": "7",
    "name": "Pipefy GPT",
    "type": "system",
    "organizationDefault": True,
    "systemDefault": True,
    "state": "active",
    "description": "Managed model",
    "aiCredits": 2,
    "deprecationDate": None,
    "configuration": {"model": "gpt-4o"},
}


def providers_connection(
    nodes: list[dict], *, has_next: bool = False, cursor: str | None = None
) -> dict:
    return {
        "allLlmProvidersByOrganization": {
            "edges": [{"node": n} for n in nodes],
            "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
        }
    }


class TestGetLlmProviders:
    @pytest.mark.anyio
    async def test_returns_both_union_members_and_page_info(self):
        executor = mock_executor(
            providers_connection([SYSTEM_NODE, BYOM_NODE], has_next=True, cursor="c1")
        )
        service = LlmProviderService(executor=executor)

        result = await service.get_llm_providers("org-uuid-1")

        assert result["providers"] == [SYSTEM_NODE, BYOM_NODE]
        assert result["page_info"] == {"hasNextPage": True, "endCursor": "c1"}
        types = {p["type"] for p in result["providers"]}
        assert types == {"system", "byom"}

    @pytest.mark.anyio
    async def test_pagination_variables_default_and_cursor(self):
        executor = mock_executor(providers_connection([]))
        service = LlmProviderService(executor=executor)

        await service.get_llm_providers("org-uuid-1")
        _, variables = executor.execute_query.await_args.args
        assert variables == {
            "organizationUuid": "org-uuid-1",
            "onlyActiveProviders": False,
            "first": 50,
        }

        await service.get_llm_providers(
            "org-uuid-1", only_active=True, first=10, after="cursor-a"
        )
        _, variables = executor.execute_query.await_args.args
        assert variables == {
            "organizationUuid": "org-uuid-1",
            "onlyActiveProviders": True,
            "first": 10,
            "after": "cursor-a",
        }

    @pytest.mark.anyio
    async def test_null_connection_yields_empty_page(self):
        executor = mock_executor({"allLlmProvidersByOrganization": None})
        service = LlmProviderService(executor=executor)

        result = await service.get_llm_providers("org-uuid-1")

        assert result == {"providers": [], "page_info": None}

    @pytest.mark.anyio
    async def test_blank_org_uuid_rejected_before_wire(self):
        executor = mock_executor({})
        service = LlmProviderService(executor=executor)

        with pytest.raises(ValueError, match="organization_uuid"):
            await service.get_llm_providers("   ")
        executor.execute_query.assert_not_awaited()


class TestGetAvailableAiModels:
    @pytest.mark.anyio
    async def test_returns_model_list(self):
        executor = mock_executor({"availableAiModels": ["gpt-4o", "gpt-4o-mini"]})
        service = LlmProviderService(executor=executor)

        models = await service.get_available_ai_models("openai")

        assert models == ["gpt-4o", "gpt-4o-mini"]
        _, variables = executor.execute_query.await_args.args
        assert variables == {"providerName": "openai"}

    @pytest.mark.anyio
    async def test_null_payload_yields_empty_list(self):
        executor = mock_executor({"availableAiModels": None})
        service = LlmProviderService(executor=executor)

        assert await service.get_available_ai_models("anthropic") == []

    @pytest.mark.anyio
    async def test_blank_provider_name_rejected(self):
        service = LlmProviderService(executor=mock_executor({}))
        with pytest.raises(ValueError, match="provider_name"):
            await service.get_available_ai_models("")


class TestGetDefaultLlmProvider:
    @pytest.mark.anyio
    async def test_organization_default_by_numeric_id(self):
        executor = mock_executor({"defaultLlmProvider": BYOM_NODE})
        service = LlmProviderService(executor=executor)

        provider = await service.get_default_llm_provider("123456")

        assert provider == BYOM_NODE
        _, variables = executor.execute_query.await_args.args
        assert variables == {"ownerType": "organization", "ownerId": "123456"}

    @pytest.mark.anyio
    async def test_custom_owner_type_passthrough(self):
        executor = mock_executor({"defaultLlmProvider": None})
        service = LlmProviderService(executor=executor)

        provider = await service.get_default_llm_provider(
            "beh-1", owner_type="behavior"
        )

        assert provider == {}
        _, variables = executor.execute_query.await_args.args
        assert variables == {"ownerType": "behavior", "ownerId": "beh-1"}

    @pytest.mark.anyio
    async def test_blank_owner_id_rejected(self):
        service = LlmProviderService(executor=mock_executor({}))
        with pytest.raises(ValueError, match="owner_id"):
            await service.get_default_llm_provider("  ")


class TestGetLlmProviderDependencies:
    @pytest.mark.anyio
    async def test_returns_dependencies_page_info_and_total(self):
        executor = mock_executor(
            {
                "providerDependencies": {
                    "edges": [
                        {"node": {"ownerId": "1", "ownerType": "organization"}},
                        {"node": {"ownerId": "77", "ownerType": "assistant"}},
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": "z"},
                    "totalCount": 2,
                }
            }
        )
        service = LlmProviderService(executor=executor)

        result = await service.get_llm_provider_dependencies("42", "org-uuid-1")

        assert result["dependencies"] == [
            {"ownerId": "1", "ownerType": "organization"},
            {"ownerId": "77", "ownerType": "assistant"},
        ]
        assert result["page_info"] == {"hasNextPage": False, "endCursor": "z"}
        assert result["total_count"] == 2
        _, variables = executor.execute_query.await_args.args
        assert variables == {
            "providerId": "42",
            "organizationUuid": "org-uuid-1",
            "first": 50,
        }

    @pytest.mark.anyio
    async def test_after_cursor_forwarded(self):
        executor = mock_executor({"providerDependencies": None})
        service = LlmProviderService(executor=executor)

        result = await service.get_llm_provider_dependencies(
            "42", "org-uuid-1", first=5, after="dep-cursor"
        )

        assert result == {"dependencies": [], "page_info": None, "total_count": None}
        _, variables = executor.execute_query.await_args.args
        assert variables["after"] == "dep-cursor"
        assert variables["first"] == 5

    @pytest.mark.anyio
    async def test_blank_provider_id_rejected(self):
        service = LlmProviderService(executor=mock_executor({}))
        with pytest.raises(ValueError, match="provider_id"):
            await service.get_llm_provider_dependencies("", "org-uuid-1")


class TestValidateLlmProviderAccess:
    @pytest.mark.anyio
    async def test_green_probe_reports_visibility_and_read_only_note(self):
        executor = mock_executor(
            execute_result=GraphQLResult(
                data=providers_connection([SYSTEM_NODE, BYOM_NODE]), errors=[]
            )
        )
        service = LlmProviderService(executor=executor)

        probe = await service.validate_llm_provider_access("org-uuid-1")

        assert probe["ok"] is True
        assert probe["system_providers_visible"] is True
        assert probe["custom_providers_visible"] is True
        assert probe["provider_count"] == 2
        assert "read access only" in probe["note"].lower()

    @pytest.mark.anyio
    async def test_empty_system_list_notes_possible_feature_gap(self):
        executor = mock_executor(
            execute_result=GraphQLResult(
                data=providers_connection([BYOM_NODE]), errors=[]
            )
        )
        service = LlmProviderService(executor=executor)

        probe = await service.validate_llm_provider_access("org-uuid-1")

        assert probe["ok"] is True
        assert probe["system_providers_visible"] is False
        assert "not by itself a permission problem" in probe["note"]

    @pytest.mark.anyio
    async def test_permission_denied_maps_to_structured_problem(self):
        executor = mock_executor(
            execute_result=GraphQLResult(
                data={"allLlmProvidersByOrganization": None},
                errors=[
                    {
                        "message": "Permission denied",
                        "extensions": {
                            "code": "PERMISSION_DENIED",
                            "correlation_id": "corr-1",
                        },
                    }
                ],
            )
        )
        service = LlmProviderService(executor=executor)

        probe = await service.validate_llm_provider_access("org-uuid-1")

        assert probe["ok"] is False
        assert probe["problem"]["kind"] == "permission_denied"
        assert probe["problem"]["code"] == "PERMISSION_DENIED"
        assert probe["problem"]["correlation_id"] == "corr-1"

    @pytest.mark.anyio
    async def test_not_found_maps_to_structured_problem(self):
        executor = mock_executor(
            execute_result=GraphQLResult(
                data={"allLlmProvidersByOrganization": None},
                errors=[
                    {
                        "message": "Couldn't find Organization with uuid bogus",
                        "extensions": {"code": "RESOURCE_NOT_FOUND"},
                    }
                ],
            )
        )
        service = LlmProviderService(executor=executor)

        probe = await service.validate_llm_provider_access("bogus")

        assert probe["ok"] is False
        assert probe["problem"]["kind"] == "not_found"

    @pytest.mark.anyio
    async def test_partial_errors_alongside_data_stay_visible(self):
        executor = mock_executor(
            execute_result=GraphQLResult(
                data=providers_connection([SYSTEM_NODE]),
                errors=[
                    {
                        "message": "Permission denied",
                        "extensions": {"code": "PERMISSION_DENIED"},
                    }
                ],
            )
        )
        service = LlmProviderService(executor=executor)

        probe = await service.validate_llm_provider_access("org-uuid-1")

        assert probe["ok"] is True
        assert probe["problem"]["kind"] == "permission_denied"
        assert "also carried GraphQL errors" in probe["note"]

    @pytest.mark.anyio
    async def test_null_data_without_errors_reports_runtime_problem(self):
        executor = mock_executor(
            execute_result=GraphQLResult(
                data={"allLlmProvidersByOrganization": None}, errors=[]
            )
        )
        service = LlmProviderService(executor=executor)

        probe = await service.validate_llm_provider_access("org-uuid-1")

        assert probe["ok"] is False
        assert probe["problem"]["kind"] == "runtime"


class TestGraphQLProblemClassifier:
    def test_code_wins_over_message(self):
        problem = classify_graphql_error_dicts(
            [
                {
                    "message": "Record not found",
                    "extensions": {"code": "PERMISSION_DENIED"},
                }
            ]
        )
        assert problem is not None
        assert problem.kind is GraphQLProblemKind.PERMISSION_DENIED

    def test_not_found_falls_back_to_message_marker(self):
        problem = classify_graphql_error_dicts(
            [{"message": "Couldn't find Repo with uuid x", "extensions": {}}]
        )
        assert problem is not None
        assert problem.kind is GraphQLProblemKind.NOT_FOUND
        assert problem.code is None

    def test_invalid_arguments_and_feature_codes(self):
        invalid = classify_graphql_error_dicts(
            [{"message": "bad", "extensions": {"code": "RECORD_INVALID"}}]
        )
        feature = classify_graphql_error_dicts(
            [{"message": "off", "extensions": {"code": "FEATURE_NOT_ENABLED"}}]
        )
        assert (
            invalid is not None and invalid.kind is GraphQLProblemKind.INVALID_ARGUMENTS
        )
        assert (
            feature is not None
            and feature.kind is GraphQLProblemKind.FEATURE_NOT_ENABLED
        )

    def test_unrecognized_error_is_runtime(self):
        problem = classify_graphql_error_dicts(
            [{"message": "boom", "extensions": {"code": "SOMETHING_ELSE"}}]
        )
        assert problem is not None
        assert problem.kind is GraphQLProblemKind.RUNTIME
        assert problem.code == "SOMETHING_ELSE"

    def test_empty_list_returns_none(self):
        assert classify_graphql_error_dicts([]) is None

    def test_classify_exception_reads_errors_attribute(self):
        class FakeTransportError(Exception):
            def __init__(self):
                super().__init__("gql error")
                self.errors = [
                    {
                        "message": "Permission denied",
                        "extensions": {"code": "PERMISSION_DENIED"},
                    }
                ]

        problem = classify_exception(FakeTransportError())
        assert problem is not None
        assert problem.kind is GraphQLProblemKind.PERMISSION_DENIED

    def test_classify_exception_without_graphql_errors_returns_none(self):
        assert classify_exception(RuntimeError("socket closed")) is None
