"""Unit tests for KnowledgeBaseService (list, plain text CRUD, access probe)."""

from __future__ import annotations

import pytest
from _shared.mock_clients import mock_executor

from pipefy_sdk.graphql_executor import GraphQLResult
from pipefy_sdk.services.knowledge_base_service import (
    MAX_PLAIN_TEXT_CONTENT_LENGTH,
    MAX_PLAIN_TEXT_DESCRIPTION_LENGTH,
    KnowledgeBaseService,
)

PLAIN_TEXT_NODE = {
    "id": "kb-1",
    "type": "knowledge_base_plain_texts",
    "name": "Onboarding",
    "description": "How to onboard",
    "updatedAt": "2026-07-17T00:00:00Z",
}

DOCUMENT_NODE = {
    "id": "kb-2",
    "type": "knowledge_base_documents",
    "name": "Handbook",
    "description": "PDF",
    "updatedAt": "2026-07-16T00:00:00Z",
}

PLAIN_TEXT_FULL = {
    "id": "kb-1",
    "name": "Onboarding",
    "description": "How to onboard",
    "content": "Step 1...",
    "updatedAt": "2026-07-17T00:00:00Z",
}


class TestGetAiKnowledgeBases:
    @pytest.mark.anyio
    async def test_returns_items(self):
        executor = mock_executor({"aiKnowledgeBases": [PLAIN_TEXT_NODE, DOCUMENT_NODE]})
        service = KnowledgeBaseService(executor=executor)

        items = await service.get_ai_knowledge_bases("pipe-uuid-1")

        assert items == [PLAIN_TEXT_NODE, DOCUMENT_NODE]
        _, variables = executor.execute_query.await_args.args
        assert variables == {"pipeUuid": "pipe-uuid-1"}

    @pytest.mark.anyio
    async def test_null_list_yields_empty(self):
        executor = mock_executor({"aiKnowledgeBases": None})
        service = KnowledgeBaseService(executor=executor)

        assert await service.get_ai_knowledge_bases("pipe-uuid-1") == []

    @pytest.mark.anyio
    async def test_blank_pipe_uuid_rejected_before_wire(self):
        executor = mock_executor({})
        service = KnowledgeBaseService(executor=executor)

        with pytest.raises(ValueError, match="pipe_uuid"):
            await service.get_ai_knowledge_bases("   ")
        executor.execute_query.assert_not_awaited()


class TestGetAiKnowledgeBasePlainText:
    @pytest.mark.anyio
    async def test_returns_plain_text(self):
        executor = mock_executor({"aiKnowledgeBasePlainText": PLAIN_TEXT_FULL})
        service = KnowledgeBaseService(executor=executor)

        result = await service.get_ai_knowledge_base_plain_text("kb-1", "pipe-uuid-1")

        assert result == PLAIN_TEXT_FULL
        _, variables = executor.execute_query.await_args.args
        assert variables == {"id": "kb-1", "pipeUuid": "pipe-uuid-1"}

    @pytest.mark.anyio
    async def test_null_yields_empty_dict(self):
        executor = mock_executor({"aiKnowledgeBasePlainText": None})
        service = KnowledgeBaseService(executor=executor)

        assert await service.get_ai_knowledge_base_plain_text("kb-x", "p") == {}


class TestCreatePlainText:
    @pytest.mark.anyio
    async def test_wraps_input_and_returns_payload(self):
        executor = mock_executor(
            {
                "createAiKnowledgeBasePlainText": {
                    "knowledgeBasePlainText": PLAIN_TEXT_FULL
                }
            }
        )
        service = KnowledgeBaseService(executor=executor)

        result = await service.create_ai_knowledge_base_plain_text(
            "pipe-uuid-1",
            name="Onboarding",
            content="Step 1...",
            description="How to onboard",
        )

        assert result == PLAIN_TEXT_FULL
        _, variables = executor.execute_query.await_args.args
        assert variables == {
            "input": {
                "pipeUuid": "pipe-uuid-1",
                "name": "Onboarding",
                "content": "Step 1...",
                "description": "How to onboard",
            }
        }

    @pytest.mark.anyio
    @pytest.mark.parametrize("field", ["name", "content", "description"])
    async def test_blank_required_field_rejected_before_wire(self, field):
        executor = mock_executor({})
        service = KnowledgeBaseService(executor=executor)
        kwargs = {
            "name": "n",
            "content": "c",
            "description": "d",
            field: "   ",
        }

        with pytest.raises(ValueError, match=field):
            await service.create_ai_knowledge_base_plain_text("p", **kwargs)
        executor.execute_query.assert_not_awaited()

    @pytest.mark.anyio
    async def test_content_over_limit_rejected(self):
        executor = mock_executor({})
        service = KnowledgeBaseService(executor=executor)

        with pytest.raises(ValueError, match="3500"):
            await service.create_ai_knowledge_base_plain_text(
                "p",
                name="n",
                content="x" * (MAX_PLAIN_TEXT_CONTENT_LENGTH + 1),
                description="d",
            )
        executor.execute_query.assert_not_awaited()

    @pytest.mark.anyio
    async def test_description_over_limit_rejected(self):
        executor = mock_executor({})
        service = KnowledgeBaseService(executor=executor)

        with pytest.raises(ValueError, match="900"):
            await service.create_ai_knowledge_base_plain_text(
                "p",
                name="n",
                content="c",
                description="y" * (MAX_PLAIN_TEXT_DESCRIPTION_LENGTH + 1),
            )
        executor.execute_query.assert_not_awaited()

    @pytest.mark.anyio
    async def test_content_at_limit_accepted(self):
        executor = mock_executor(
            {
                "createAiKnowledgeBasePlainText": {
                    "knowledgeBasePlainText": PLAIN_TEXT_FULL
                }
            }
        )
        service = KnowledgeBaseService(executor=executor)

        await service.create_ai_knowledge_base_plain_text(
            "p",
            name="n",
            content="x" * MAX_PLAIN_TEXT_CONTENT_LENGTH,
            description="d",
        )
        executor.execute_query.assert_awaited_once()

    @pytest.mark.anyio
    async def test_null_payload_without_errors_is_a_failure(self):
        executor = mock_executor(
            {"createAiKnowledgeBasePlainText": {"knowledgeBasePlainText": None}}
        )
        service = KnowledgeBaseService(executor=executor)

        with pytest.raises(ValueError, match="no plain text payload"):
            await service.create_ai_knowledge_base_plain_text(
                "p", name="n", content="c", description="d"
            )


class TestUpdatePlainText:
    @pytest.mark.anyio
    async def test_only_sends_provided_fields(self):
        executor = mock_executor(
            {
                "updateAiKnowledgeBasePlainText": {
                    "knowledgeBasePlainText": PLAIN_TEXT_FULL
                }
            }
        )
        service = KnowledgeBaseService(executor=executor)

        await service.update_ai_knowledge_base_plain_text(
            "kb-1", "pipe-uuid-1", content="New content"
        )

        _, variables = executor.execute_query.await_args.args
        assert variables == {
            "input": {
                "pipeUuid": "pipe-uuid-1",
                "plainTextId": "kb-1",
                "content": "New content",
            }
        }

    @pytest.mark.anyio
    async def test_no_fields_rejected_before_wire(self):
        executor = mock_executor({})
        service = KnowledgeBaseService(executor=executor)

        with pytest.raises(ValueError, match="at least one"):
            await service.update_ai_knowledge_base_plain_text("kb-1", "pipe-uuid-1")
        executor.execute_query.assert_not_awaited()

    @pytest.mark.anyio
    async def test_provided_field_validated(self):
        executor = mock_executor({})
        service = KnowledgeBaseService(executor=executor)

        with pytest.raises(ValueError, match="3500"):
            await service.update_ai_knowledge_base_plain_text(
                "kb-1", "p", content="x" * (MAX_PLAIN_TEXT_CONTENT_LENGTH + 1)
            )
        executor.execute_query.assert_not_awaited()

    @pytest.mark.anyio
    async def test_null_payload_without_errors_is_a_failure(self):
        executor = mock_executor(
            {"updateAiKnowledgeBasePlainText": {"knowledgeBasePlainText": None}}
        )
        service = KnowledgeBaseService(executor=executor)

        with pytest.raises(ValueError, match="no plain text payload"):
            await service.update_ai_knowledge_base_plain_text("kb-1", "p", content="c")


class TestDeletePlainText:
    @pytest.mark.anyio
    async def test_success(self):
        executor = mock_executor(
            {"deleteAiKnowledgeBasePlainText": {"success": True, "errors": []}}
        )
        service = KnowledgeBaseService(executor=executor)

        result = await service.delete_ai_knowledge_base_plain_text("kb-1", "p")

        assert result == {"success": True, "errors": []}
        _, variables = executor.execute_query.await_args.args
        assert variables == {"input": {"pipeUuid": "p", "plainTextId": "kb-1"}}

    @pytest.mark.anyio
    async def test_failure_surfaces_errors(self):
        executor = mock_executor(
            {"deleteAiKnowledgeBasePlainText": {"success": False, "errors": ["nope"]}}
        )
        service = KnowledgeBaseService(executor=executor)

        result = await service.delete_ai_knowledge_base_plain_text("kb-1", "p")

        assert result == {"success": False, "errors": ["nope"]}


class TestValidateKnowledgeBaseAccess:
    @pytest.mark.anyio
    async def test_green_probe_reports_count_and_read_only_note(self):
        executor = mock_executor(
            execute_result=GraphQLResult(
                data={"aiKnowledgeBases": [PLAIN_TEXT_NODE, DOCUMENT_NODE]}, errors=[]
            )
        )
        service = KnowledgeBaseService(executor=executor)

        probe = await service.validate_knowledge_base_access("pipe-uuid-1")

        assert probe["ok"] is True
        assert probe["knowledge_base_count"] == 2
        assert "read access only" in probe["note"].lower()
        assert "manage_ai_agents" in probe["note"]

    @pytest.mark.anyio
    async def test_empty_list_is_still_ok(self):
        executor = mock_executor(
            execute_result=GraphQLResult(data={"aiKnowledgeBases": []}, errors=[])
        )
        service = KnowledgeBaseService(executor=executor)

        probe = await service.validate_knowledge_base_access("pipe-uuid-1")

        assert probe["ok"] is True
        assert probe["knowledge_base_count"] == 0

    @pytest.mark.anyio
    async def test_permission_denied_maps_to_structured_problem(self):
        executor = mock_executor(
            execute_result=GraphQLResult(
                data={"aiKnowledgeBases": None},
                errors=[
                    {
                        "message": "Permission denied",
                        "extensions": {
                            "code": "PERMISSION_DENIED",
                            "correlation_id": "corr-9",
                        },
                    }
                ],
            )
        )
        service = KnowledgeBaseService(executor=executor)

        probe = await service.validate_knowledge_base_access("pipe-uuid-1")

        assert probe["ok"] is False
        assert probe["problem"]["kind"] == "permission_denied"
        assert probe["problem"]["correlation_id"] == "corr-9"

    @pytest.mark.anyio
    async def test_not_found_maps_to_structured_problem(self):
        executor = mock_executor(
            execute_result=GraphQLResult(
                data={"aiKnowledgeBases": None},
                errors=[
                    {
                        "message": "Couldn't find Pipe with uuid bogus",
                        "extensions": {"code": "RESOURCE_NOT_FOUND"},
                    }
                ],
            )
        )
        service = KnowledgeBaseService(executor=executor)

        probe = await service.validate_knowledge_base_access("bogus")

        assert probe["ok"] is False
        assert probe["problem"]["kind"] == "not_found"

    @pytest.mark.anyio
    async def test_partial_errors_alongside_data_stay_visible(self):
        executor = mock_executor(
            execute_result=GraphQLResult(
                data={"aiKnowledgeBases": [PLAIN_TEXT_NODE]},
                errors=[
                    {
                        "message": "Permission denied",
                        "extensions": {"code": "PERMISSION_DENIED"},
                    }
                ],
            )
        )
        service = KnowledgeBaseService(executor=executor)

        probe = await service.validate_knowledge_base_access("pipe-uuid-1")

        assert probe["ok"] is True
        assert probe["problem"]["kind"] == "permission_denied"
        assert "also carried GraphQL errors" in probe["note"]

    @pytest.mark.anyio
    async def test_null_data_without_errors_reports_runtime_problem(self):
        executor = mock_executor(
            execute_result=GraphQLResult(data={"aiKnowledgeBases": None}, errors=[])
        )
        service = KnowledgeBaseService(executor=executor)

        probe = await service.validate_knowledge_base_access("pipe-uuid-1")

        assert probe["ok"] is False
        assert probe["problem"]["kind"] == "runtime"
