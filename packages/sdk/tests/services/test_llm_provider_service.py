"""Unit tests for LlmProviderService and the shared GraphQL problem classifier."""

from __future__ import annotations

import json

import pytest
from _shared.mock_clients import mock_executor
from graphql import print_ast

from pipefy_sdk.graphql_executor import GraphQLResult
from pipefy_sdk.graphql_problem import (
    GraphQLProblemKind,
    classify_exception,
    classify_graphql_error_dicts,
)
from pipefy_sdk.queries.llm_provider_queries import (
    CREATE_LLM_PROVIDER_MUTATION,
    UPDATE_LLM_PROVIDER_MUTATION,
)
from pipefy_sdk.services.llm_provider_service import (
    LlmProviderService,
    _read_configuration_object,
)

# A configuration file always holds at least one secret; tests assert it never
# leaks into a response, an error, or the static mutation document.
SECRET = "sk-SUPER-SECRET-TOKEN"
WRITTEN_PROVIDER = {
    "id": "42",
    "name": "My OpenAI",
    "type": "byom",
    "active": True,
    "organizationDefault": False,
}


def _config_file(tmp_path, payload) -> str:
    path = tmp_path / "config.json"
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload))
    return str(path)


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

    def test_blank_or_whitespace_message_becomes_unknown_error(self):
        for raw in ("", "   ", None):
            problem = classify_graphql_error_dicts(
                [{"message": raw, "extensions": {"code": "PERMISSION_DENIED"}}]
            )
            assert problem is not None
            assert problem.message == "Unknown error"
            assert problem.kind is GraphQLProblemKind.PERMISSION_DENIED

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


class TestConfigurationSecrecyInvariants:
    def test_create_and_update_documents_never_select_configuration(self):
        """The mutation payloads must not request `configuration` (secret echo)."""

        def _text(node) -> str:
            return print_ast(getattr(node, "document", node))

        assert "configuration" not in _text(CREATE_LLM_PROVIDER_MUTATION)
        assert "configuration" not in _text(UPDATE_LLM_PROVIDER_MUTATION)

    def test_valid_object_parsed(self, tmp_path):
        cfg = {"provider": "openai", "auth": {"token": SECRET}}
        assert _read_configuration_object(_config_file(tmp_path, cfg)) == cfg

    def test_missing_file_error_has_no_contents(self, tmp_path):
        with pytest.raises(ValueError, match="Could not read configuration file"):
            _read_configuration_object(str(tmp_path / "nope.json"))

    def test_invalid_json_error_never_echoes_secret(self, tmp_path):
        # A secret-bearing but malformed file: the parse error must not leak it.
        path = _config_file(tmp_path, f'{{"auth": {{"token": "{SECRET}"}} TRAILING')
        with pytest.raises(ValueError) as exc:
            _read_configuration_object(path)
        assert SECRET not in str(exc.value)
        assert "not valid JSON" in str(exc.value)

    def test_non_object_value_rejected_without_echoing_secret(self, tmp_path):
        # A bare JSON string that happens to be a secret must not be echoed.
        path = _config_file(tmp_path, json.dumps(SECRET))
        with pytest.raises(ValueError, match="non-empty JSON object"):
            _read_configuration_object(path)
        with pytest.raises(ValueError) as exc:
            _read_configuration_object(path)
        assert SECRET not in str(exc.value)

    def test_empty_object_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="non-empty JSON object"):
            _read_configuration_object(_config_file(tmp_path, {}))

    def test_oversized_file_rejected(self, tmp_path):
        path = tmp_path / "big.json"
        path.write_text('{"x": "' + "a" * (256 * 1024) + '"}')
        with pytest.raises(ValueError, match="exceeds"):
            _read_configuration_object(str(path))


class TestCreateLlmProvider:
    @pytest.mark.anyio
    async def test_sends_configuration_from_file_and_returns_provider(self, tmp_path):
        executor = mock_executor(
            {"createLlmProvider": {"llmProvider": WRITTEN_PROVIDER}}
        )
        service = LlmProviderService(executor=executor)
        cfg = {"provider": "openai", "model": "gpt-4o", "auth": {"token": SECRET}}

        provider = await service.create_llm_provider(
            "org-uuid-1",
            name="My OpenAI",
            configuration_file_path=_config_file(tmp_path, cfg),
        )

        assert provider == WRITTEN_PROVIDER
        assert "configuration" not in provider  # secret never returned
        _, variables = executor.execute_query.await_args.args
        assert variables["input"]["configuration"] == cfg
        assert variables["input"]["name"] == "My OpenAI"
        assert variables["input"]["organizationUuid"] == "org-uuid-1"

    @pytest.mark.anyio
    async def test_blank_name_rejected_before_wire(self, tmp_path):
        executor = mock_executor({})
        service = LlmProviderService(executor=executor)
        with pytest.raises(ValueError, match="name"):
            await service.create_llm_provider(
                "org-uuid-1",
                name="  ",
                configuration_file_path=_config_file(tmp_path, {"provider": "openai"}),
            )
        executor.execute_query.assert_not_awaited()

    @pytest.mark.anyio
    async def test_null_payload_reads_as_failure(self, tmp_path):
        executor = mock_executor({"createLlmProvider": {"llmProvider": None}})
        service = LlmProviderService(executor=executor)
        with pytest.raises(ValueError, match="may not have persisted"):
            await service.create_llm_provider(
                "org-uuid-1",
                name="X",
                configuration_file_path=_config_file(tmp_path, {"provider": "openai"}),
            )


class TestUpdateLlmProvider:
    @pytest.mark.anyio
    async def test_full_replacement_configuration_required_and_sent(self, tmp_path):
        executor = mock_executor(
            {"updateLlmProvider": {"llmProvider": WRITTEN_PROVIDER}}
        )
        service = LlmProviderService(executor=executor)
        cfg = {"provider": "openai", "model": "gpt-4o-mini", "auth": {"token": SECRET}}

        provider = await service.update_llm_provider(
            "42",
            "org-uuid-1",
            configuration_file_path=_config_file(tmp_path, cfg),
            name="Renamed",
        )

        assert provider == WRITTEN_PROVIDER
        _, variables = executor.execute_query.await_args.args
        assert variables["input"]["configuration"] == cfg
        assert variables["input"]["id"] == "42"
        assert variables["input"]["name"] == "Renamed"

    @pytest.mark.anyio
    async def test_name_omitted_when_not_given(self, tmp_path):
        executor = mock_executor(
            {"updateLlmProvider": {"llmProvider": WRITTEN_PROVIDER}}
        )
        service = LlmProviderService(executor=executor)
        await service.update_llm_provider(
            "42",
            "org-uuid-1",
            configuration_file_path=_config_file(tmp_path, {"provider": "openai"}),
        )
        _, variables = executor.execute_query.await_args.args
        assert "name" not in variables["input"]

    @pytest.mark.anyio
    async def test_redaction_placeholder_passed_through_unchanged(self, tmp_path):
        """Sending back a fetched config keeps the placeholder — backend preserves."""
        executor = mock_executor(
            {"updateLlmProvider": {"llmProvider": WRITTEN_PROVIDER}}
        )
        service = LlmProviderService(executor=executor)
        cfg = {"provider": "openai", "auth": {"token": "__REDACTED__"}}

        await service.update_llm_provider(
            "42",
            "org-uuid-1",
            configuration_file_path=_config_file(tmp_path, cfg),
        )
        _, variables = executor.execute_query.await_args.args
        assert variables["input"]["configuration"]["auth"]["token"] == "__REDACTED__"


class TestDeleteLlmProvider:
    @pytest.mark.anyio
    async def test_returns_success_and_sends_id_org(self):
        executor = mock_executor({"deleteLlmProvider": {"success": True}})
        service = LlmProviderService(executor=executor)

        result = await service.delete_llm_provider("42", "org-uuid-1")

        assert result == {"success": True}
        _, variables = executor.execute_query.await_args.args
        assert variables["input"] == {"id": "42", "organizationUuid": "org-uuid-1"}

    @pytest.mark.anyio
    async def test_null_success_reads_as_false(self):
        executor = mock_executor({"deleteLlmProvider": {"success": None}})
        service = LlmProviderService(executor=executor)
        assert await service.delete_llm_provider("42", "org-uuid-1") == {
            "success": False
        }


class TestSetLlmProviderActiveStatus:
    @pytest.mark.anyio
    async def test_sends_provider_id_and_active_flag(self):
        executor = mock_executor({"setLlmProviderActiveStatus": {"success": True}})
        service = LlmProviderService(executor=executor)

        result = await service.set_llm_provider_active_status("42", active=False)

        assert result == {"success": True}
        _, variables = executor.execute_query.await_args.args
        assert variables["input"] == {"providerId": "42", "active": False}


class TestSetDefaultLlmProvider:
    @pytest.mark.anyio
    async def test_custom_provider_id_sets_organization_owner(self):
        active = {
            "id": "a1",
            "ownerId": "123456",
            "ownerType": "organization",
            "llmProviderId": "42",
            "systemLlmProviderId": None,
        }
        executor = mock_executor(
            {"setActiveLlmProvider": {"activeLlmProvider": active}}
        )
        service = LlmProviderService(executor=executor)

        result = await service.set_default_llm_provider("123456", provider_id="42")

        assert result == active
        _, variables = executor.execute_query.await_args.args
        assert variables["input"] == {
            "ownerId": "123456",
            "ownerType": "organization",
            "providerId": "42",
        }

    @pytest.mark.anyio
    async def test_system_provider_id_uses_system_key(self):
        executor = mock_executor(
            {"setActiveLlmProvider": {"activeLlmProvider": {"id": "a2"}}}
        )
        service = LlmProviderService(executor=executor)

        await service.set_default_llm_provider("123456", system_provider_id="7")

        _, variables = executor.execute_query.await_args.args
        assert variables["input"]["systemProviderId"] == "7"
        assert "providerId" not in variables["input"]

    @pytest.mark.anyio
    async def test_both_ids_rejected(self):
        executor = mock_executor({})
        service = LlmProviderService(executor=executor)
        with pytest.raises(ValueError, match="exactly one"):
            await service.set_default_llm_provider(
                "123456", provider_id="42", system_provider_id="7"
            )
        executor.execute_query.assert_not_awaited()

    @pytest.mark.anyio
    async def test_neither_id_rejected(self):
        executor = mock_executor({})
        service = LlmProviderService(executor=executor)
        with pytest.raises(ValueError, match="exactly one"):
            await service.set_default_llm_provider("123456")
        executor.execute_query.assert_not_awaited()


class TestResetDefaultLlmProvider:
    @pytest.mark.anyio
    async def test_sends_organization_owner_and_returns_success(self):
        executor = mock_executor({"resetLlmProviderOwner": {"success": True}})
        service = LlmProviderService(executor=executor)

        result = await service.reset_default_llm_provider("123456")

        assert result == {"success": True}
        _, variables = executor.execute_query.await_args.args
        assert variables["input"] == {
            "ownerId": "123456",
            "ownerType": "organization",
        }
