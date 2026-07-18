"""Unit tests for KnowledgeBaseService (list, plain text CRUD, access probe)."""

from __future__ import annotations

import pytest
from _shared.mock_clients import mock_executor

from pipefy_sdk.graphql_executor import GraphQLResult
from pipefy_sdk.services import knowledge_base_service as kb_module
from pipefy_sdk.services.knowledge_base_service import (
    MAX_DOCUMENT_DESCRIPTION_LENGTH,
    MAX_PLAIN_TEXT_CONTENT_LENGTH,
    MAX_PLAIN_TEXT_DESCRIPTION_LENGTH,
    KnowledgeBaseService,
)
from pipefy_sdk.services.types import KnowledgeBaseDocumentUploadError

DOCUMENT_FULL = {
    "id": "kb-2",
    "name": "Handbook",
    "description": "Company handbook",
    "content": "https://app.pipefy.com/storage/v1/signed/orgs/o/uploads/u/h.pdf?sig=x",
    "updatedAt": "2026-07-16T00:00:00Z",
}

_UPLOAD_URL = "https://pipefy-prd.s3.amazonaws.com/orgs/o/uploads/u/h.pdf?X-Amz=1"
_DOWNLOAD_URL = (
    "https://app.pipefy.com/storage/v1/signed/orgs/o/uploads/u/h.pdf?signature=x"
)
_PDF_BYTES = b"%PDF-1.4 fake pdf body"


class _FakeUploader:
    """S3Uploader test double: records the PUT and returns a canned result."""

    def __init__(self, result: dict | None = None, error: Exception | None = None):
        self.result = result if result is not None else {"status_code": 200}
        self.error = error
        self.calls: list[dict] = []

    async def put(self, *, url: str, bytes_: bytes, content_type: str | None) -> dict:
        self.calls.append({"url": url, "bytes_": bytes_, "content_type": content_type})
        if self.error is not None:
            raise self.error
        return self.result


def _write_pdf(tmp_path, name: str = "handbook.pdf", data: bytes = _PDF_BYTES):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _create_flow_executor():
    """Executor whose three ``execute_query`` calls drive a full create flow."""
    return mock_executor(
        side_effect=[
            {"pipe": {"organization": {"id": "300514213", "uuid": "org-uuid"}}},
            {"createPresignedUrl": {"url": _UPLOAD_URL, "downloadUrl": _DOWNLOAD_URL}},
            {"createAiKnowledgeBaseDocument": {"knowledgeBaseDocument": DOCUMENT_FULL}},
        ]
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


class TestGetDocument:
    @pytest.mark.anyio
    async def test_returns_document(self):
        executor = mock_executor({"aiKnowledgeBaseDocument": DOCUMENT_FULL})
        service = KnowledgeBaseService(executor=executor)

        result = await service.get_ai_knowledge_base_document("kb-2", "pipe-uuid-1")

        assert result == DOCUMENT_FULL
        _, variables = executor.execute_query.await_args.args
        assert variables == {"id": "kb-2", "pipeUuid": "pipe-uuid-1"}

    @pytest.mark.anyio
    async def test_null_yields_empty_dict(self):
        executor = mock_executor({"aiKnowledgeBaseDocument": None})
        service = KnowledgeBaseService(executor=executor)

        assert await service.get_ai_knowledge_base_document("kb-x", "p") == {}


class TestCreateDocument:
    @pytest.mark.anyio
    async def test_full_pipeline_sends_expected_wire_calls(self, tmp_path):
        executor = _create_flow_executor()
        uploader = _FakeUploader()
        service = KnowledgeBaseService(executor=executor, s3_uploader=uploader)
        pdf = _write_pdf(tmp_path)

        result = await service.create_ai_knowledge_base_document(
            "pipe-uuid-1",
            name="Handbook",
            description="Company handbook",
            file_path=pdf,
        )

        assert result == DOCUMENT_FULL
        calls = executor.execute_query.await_args_list
        # 1) resolve org from pipe uuid
        assert calls[0].args[1] == {"id": "pipe-uuid-1"}
        # 2) presign with the resolved org id, file name, pdf type, and byte length
        assert calls[1].args[1] == {
            "organizationId": "300514213",
            "fileName": "handbook.pdf",
            "contentType": "application/pdf",
            "contentLength": len(_PDF_BYTES),
        }
        # 3) create mutation stores the persistent download URL as documentUrl
        assert calls[2].args[1] == {
            "input": {
                "pipeUuid": "pipe-uuid-1",
                "name": "Handbook",
                "description": "Company handbook",
                "documentUrl": _DOWNLOAD_URL,
            }
        }
        # the bytes were PUT to the single-use upload URL, not the download URL
        assert uploader.calls == [
            {
                "url": _UPLOAD_URL,
                "bytes_": _PDF_BYTES,
                "content_type": "application/pdf",
            }
        ]

    @pytest.mark.anyio
    async def test_non_pdf_rejected_at_file_read_before_any_io(self, tmp_path):
        executor = _create_flow_executor()
        uploader = _FakeUploader()
        service = KnowledgeBaseService(executor=executor, s3_uploader=uploader)
        txt = _write_pdf(tmp_path, name="notes.txt")

        with pytest.raises(KnowledgeBaseDocumentUploadError) as exc_info:
            await service.create_ai_knowledge_base_document(
                "p", name="n", description="d", file_path=txt
            )

        assert exc_info.value.step == "file_read"
        assert ".pdf" in str(exc_info.value)
        executor.execute_query.assert_not_awaited()
        assert uploader.calls == []

    @pytest.mark.anyio
    async def test_uppercase_pdf_extension_accepted(self, tmp_path):
        executor = _create_flow_executor()
        service = KnowledgeBaseService(executor=executor, s3_uploader=_FakeUploader())
        pdf = _write_pdf(tmp_path, name="Handbook.PDF")

        result = await service.create_ai_knowledge_base_document(
            "p", name="n", description="d", file_path=pdf
        )

        assert result == DOCUMENT_FULL

    @pytest.mark.anyio
    async def test_size_cap_rejected_at_file_read(self, tmp_path, monkeypatch):
        monkeypatch.setattr(kb_module, "MAX_DOCUMENT_SIZE_BYTES", 8)
        executor = _create_flow_executor()
        uploader = _FakeUploader()
        service = KnowledgeBaseService(executor=executor, s3_uploader=uploader)
        pdf = _write_pdf(tmp_path, data=b"%PDF-1.4 this is well over eight bytes")

        with pytest.raises(KnowledgeBaseDocumentUploadError) as exc_info:
            await service.create_ai_knowledge_base_document(
                "p", name="n", description="d", file_path=pdf
            )

        assert exc_info.value.step == "file_read"
        executor.execute_query.assert_not_awaited()
        assert uploader.calls == []

    @pytest.mark.anyio
    @pytest.mark.parametrize("field", ["name", "description"])
    async def test_blank_required_field_rejected_before_io(self, tmp_path, field):
        executor = _create_flow_executor()
        uploader = _FakeUploader()
        service = KnowledgeBaseService(executor=executor, s3_uploader=uploader)
        pdf = _write_pdf(tmp_path)
        kwargs = {"name": "n", "description": "d", field: "   "}

        with pytest.raises(ValueError, match=field):
            await service.create_ai_knowledge_base_document(
                "p", file_path=pdf, **kwargs
            )
        executor.execute_query.assert_not_awaited()
        assert uploader.calls == []

    @pytest.mark.anyio
    async def test_description_over_limit_rejected(self, tmp_path):
        executor = _create_flow_executor()
        service = KnowledgeBaseService(executor=executor, s3_uploader=_FakeUploader())
        pdf = _write_pdf(tmp_path)

        with pytest.raises(ValueError, match="900"):
            await service.create_ai_knowledge_base_document(
                "p",
                name="n",
                description="y" * (MAX_DOCUMENT_DESCRIPTION_LENGTH + 1),
                file_path=pdf,
            )
        executor.execute_query.assert_not_awaited()

    @pytest.mark.anyio
    async def test_org_resolution_failure_tagged_presigned_url(self, tmp_path):
        executor = mock_executor(side_effect=[{"pipe": None}])
        uploader = _FakeUploader()
        service = KnowledgeBaseService(executor=executor, s3_uploader=uploader)
        pdf = _write_pdf(tmp_path)

        with pytest.raises(KnowledgeBaseDocumentUploadError) as exc_info:
            await service.create_ai_knowledge_base_document(
                "p", name="n", description="d", file_path=pdf
            )

        assert exc_info.value.step == "presigned_url"
        assert uploader.calls == []

    @pytest.mark.anyio
    async def test_missing_upload_url_tagged_presigned_url(self, tmp_path):
        executor = mock_executor(
            side_effect=[
                {"pipe": {"organization": {"id": "300514213"}}},
                {"createPresignedUrl": {"url": None, "downloadUrl": _DOWNLOAD_URL}},
            ]
        )
        uploader = _FakeUploader()
        service = KnowledgeBaseService(executor=executor, s3_uploader=uploader)
        pdf = _write_pdf(tmp_path)

        with pytest.raises(KnowledgeBaseDocumentUploadError) as exc_info:
            await service.create_ai_knowledge_base_document(
                "p", name="n", description="d", file_path=pdf
            )

        assert exc_info.value.step == "presigned_url"
        assert uploader.calls == []

    @pytest.mark.anyio
    async def test_s3_failure_tagged_and_carries_snippet(self, tmp_path):
        executor = mock_executor(
            side_effect=[
                {"pipe": {"organization": {"id": "300514213"}}},
                {
                    "createPresignedUrl": {
                        "url": _UPLOAD_URL,
                        "downloadUrl": _DOWNLOAD_URL,
                    }
                },
            ]
        )
        uploader = _FakeUploader(
            result={"status_code": 403, "body_snippet": "AccessDenied"}
        )
        service = KnowledgeBaseService(executor=executor, s3_uploader=uploader)
        pdf = _write_pdf(tmp_path)

        with pytest.raises(KnowledgeBaseDocumentUploadError) as exc_info:
            await service.create_ai_knowledge_base_document(
                "p", name="n", description="d", file_path=pdf
            )

        assert exc_info.value.step == "s3_upload"
        assert exc_info.value.status_code == 403
        assert exc_info.value.body_snippet == "AccessDenied"
        # the create mutation (third call) never ran
        assert executor.execute_query.await_count == 2

    @pytest.mark.anyio
    async def test_s3_put_exception_tagged_s3_upload(self, tmp_path):
        """A raising PUT (transport error, allowlist rejection) carries the step tag."""
        executor = mock_executor(
            side_effect=[
                {"pipe": {"organization": {"id": "300514213"}}},
                {
                    "createPresignedUrl": {
                        "url": _UPLOAD_URL,
                        "downloadUrl": _DOWNLOAD_URL,
                    }
                },
            ]
        )
        uploader = _FakeUploader(error=ConnectionError("connection reset by peer"))
        service = KnowledgeBaseService(executor=executor, s3_uploader=uploader)
        pdf = _write_pdf(tmp_path)

        with pytest.raises(KnowledgeBaseDocumentUploadError) as exc_info:
            await service.create_ai_knowledge_base_document(
                "p", name="n", description="d", file_path=pdf
            )

        assert exc_info.value.step == "s3_upload"
        assert "connection reset by peer" in str(exc_info.value)
        # the create mutation (third call) never ran
        assert executor.execute_query.await_count == 2

    @pytest.mark.anyio
    async def test_create_mutation_failure_tagged_kb_create(self, tmp_path):
        executor = mock_executor(
            side_effect=[
                {"pipe": {"organization": {"id": "300514213"}}},
                {
                    "createPresignedUrl": {
                        "url": _UPLOAD_URL,
                        "downloadUrl": _DOWNLOAD_URL,
                    }
                },
                RuntimeError("mutation boom"),
            ]
        )
        service = KnowledgeBaseService(executor=executor, s3_uploader=_FakeUploader())
        pdf = _write_pdf(tmp_path)

        with pytest.raises(KnowledgeBaseDocumentUploadError) as exc_info:
            await service.create_ai_knowledge_base_document(
                "p", name="n", description="d", file_path=pdf
            )

        assert exc_info.value.step == "kb_create"


class TestUpdateDocument:
    @pytest.mark.anyio
    async def test_only_sends_provided_fields(self):
        executor = mock_executor(
            {"updateAiKnowledgeBaseDocument": {"knowledgeBaseDocument": DOCUMENT_FULL}}
        )
        service = KnowledgeBaseService(executor=executor)

        await service.update_ai_knowledge_base_document(
            "kb-2", "pipe-uuid-1", name="New name"
        )

        _, variables = executor.execute_query.await_args.args
        assert variables == {
            "input": {
                "pipeUuid": "pipe-uuid-1",
                "documentId": "kb-2",
                "name": "New name",
            }
        }

    @pytest.mark.anyio
    async def test_no_fields_rejected_before_wire(self):
        executor = mock_executor({})
        service = KnowledgeBaseService(executor=executor)

        with pytest.raises(ValueError, match="at least one"):
            await service.update_ai_knowledge_base_document("kb-2", "pipe-uuid-1")
        executor.execute_query.assert_not_awaited()

    @pytest.mark.anyio
    async def test_description_over_limit_rejected(self):
        executor = mock_executor({})
        service = KnowledgeBaseService(executor=executor)

        with pytest.raises(ValueError, match="900"):
            await service.update_ai_knowledge_base_document(
                "kb-2", "p", description="y" * (MAX_DOCUMENT_DESCRIPTION_LENGTH + 1)
            )
        executor.execute_query.assert_not_awaited()


class TestDeleteDocument:
    @pytest.mark.anyio
    async def test_success(self):
        executor = mock_executor(
            {"deleteAiKnowledgeBaseDocument": {"success": True, "errors": []}}
        )
        service = KnowledgeBaseService(executor=executor)

        result = await service.delete_ai_knowledge_base_document("kb-2", "p")

        assert result == {"success": True, "errors": []}
        _, variables = executor.execute_query.await_args.args
        assert variables == {"input": {"pipeUuid": "p", "documentId": "kb-2"}}

    @pytest.mark.anyio
    async def test_failure_surfaces_errors(self):
        executor = mock_executor(
            {"deleteAiKnowledgeBaseDocument": {"success": False, "errors": ["nope"]}}
        )
        service = KnowledgeBaseService(executor=executor)

        result = await service.delete_ai_knowledge_base_document("kb-2", "p")

        assert result == {"success": False, "errors": ["nope"]}
