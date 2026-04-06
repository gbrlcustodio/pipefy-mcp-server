"""Unit tests for AttachmentService and attachment GraphQL constants."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from graphql import print_ast

from pipefy_mcp.services.pipefy.attachment_service import AttachmentService
from pipefy_mcp.services.pipefy.client import PipefyClient
from pipefy_mcp.services.pipefy.queries.attachment_queries import (
    CREATE_PRESIGNED_URL_MUTATION,
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
    service = AttachmentService(settings=mock_settings)
    service.execute_query = AsyncMock(return_value=return_value)
    return service


@pytest.mark.unit
def test_create_presigned_url_mutation_document_shape():
    doc = print_ast(CREATE_PRESIGNED_URL_MUTATION)
    lowered = doc.lower()
    stripped_lines = {ln.strip() for ln in doc.splitlines()}
    assert "createpresignedurl" in lowered
    assert "url" in stripped_lines
    assert "downloadUrl" in stripped_lines
    assert "clientMutationId" in stripped_lines
    assert "$organizationId" in doc
    assert "$fileName" in doc
    assert "$contentType" in doc
    assert "$contentLength" in doc


@pytest.mark.unit
def test_extract_storage_path_standard_presigned_url():
    url = (
        "https://pipefy-uploads.s3.amazonaws.com/orgs/550e8400-e29b-41d4-a716-446655440000/"
        "uploads/660e8400-e29b-41d4-a716-446655440001/report.pdf"
        "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=test"
    )
    expected = (
        "orgs/550e8400-e29b-41d4-a716-446655440000/"
        "uploads/660e8400-e29b-41d4-a716-446655440001/report.pdf"
    )
    assert AttachmentService.extract_storage_path(url) == expected


@pytest.mark.unit
def test_extract_storage_path_special_characters_in_filename():
    url = (
        "https://bucket.s3.us-east-1.amazonaws.com/orgs/u1/uploads/u2/"
        "my%20file%20%C3%A9t%C3%A9.txt?signature=abc"
    )
    assert (
        AttachmentService.extract_storage_path(url)
        == "orgs/u1/uploads/u2/my file été.txt"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_url",
    [
        "https://example.com",
        "https://example.com/",
        "https://example.com/?q=1",
    ],
)
def test_extract_storage_path_empty_path_raises(bad_url):
    with pytest.raises(ValueError, match="no object path"):
        AttachmentService.extract_storage_path(bad_url)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_presigned_url_success(mock_settings):
    payload = {
        "createPresignedUrl": {
            "url": "https://s3.example.com/put?sig=1",
            "downloadUrl": "https://app.pipefy.com/files/dl/xyz",
            "clientMutationId": "cm1",
        }
    }
    service = _make_service(mock_settings, payload)
    result = await service.create_presigned_url("42", "doc.pdf")

    service.execute_query.assert_awaited_once()
    query, variables = service.execute_query.call_args[0]
    assert query is CREATE_PRESIGNED_URL_MUTATION
    assert variables["organizationId"] == "42"
    assert variables["fileName"] == "doc.pdf"
    assert variables["contentType"] is None
    assert variables["contentLength"] is None
    assert result["url"] == "https://s3.example.com/put?sig=1"
    assert result["download_url"] == "https://app.pipefy.com/files/dl/xyz"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_presigned_url_with_optional_fields(mock_settings):
    payload = {
        "createPresignedUrl": {
            "url": "https://s3.example.com/put",
            "downloadUrl": "https://dl",
            "clientMutationId": None,
        }
    }
    service = _make_service(mock_settings, payload)
    await service.create_presigned_url(
        "99",
        "a.bin",
        content_type="application/octet-stream",
        content_length=1024,
    )
    variables = service.execute_query.call_args[0][1]
    assert variables["organizationId"] == "99"
    assert variables["fileName"] == "a.bin"
    assert variables["contentType"] == "application/octet-stream"
    assert variables["contentLength"] == 1024


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_file_to_s3_success(mock_settings):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = ""
    mock_inner = MagicMock()
    mock_inner.put = AsyncMock(return_value=mock_response)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_inner)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    service = AttachmentService(settings=mock_settings)
    with patch("httpx.AsyncClient", return_value=mock_cm):
        result = await service.upload_file_to_s3(
            "https://s3.example.com/presigned",
            b"hello",
            content_type=None,
        )

    assert result == {"status_code": 200}
    mock_inner.put.assert_awaited_once()
    call_kw = mock_inner.put.call_args.kwargs
    assert call_kw["content"] == b"hello"
    assert call_kw["headers"] == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_file_to_s3_forbidden_includes_body_snippet(mock_settings):
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.text = "<?xml version='1.0'?><Error><Code>AccessDenied</Code></Error>"
    mock_inner = MagicMock()
    mock_inner.put = AsyncMock(return_value=mock_response)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_inner)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    service = AttachmentService(settings=mock_settings)
    with patch("httpx.AsyncClient", return_value=mock_cm):
        result = await service.upload_file_to_s3(
            "https://s3.example.com/presigned",
            b"x",
            content_type=None,
        )

    assert result["status_code"] == 403
    assert "body_snippet" in result
    assert "AccessDenied" in result["body_snippet"]
    assert "presigned" not in result["body_snippet"].lower()
    assert "https://" not in result["body_snippet"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_file_to_s3_sets_content_type_header(mock_settings):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = ""
    mock_inner = MagicMock()
    mock_inner.put = AsyncMock(return_value=mock_response)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_inner)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    service = AttachmentService(settings=mock_settings)
    with patch("httpx.AsyncClient", return_value=mock_cm):
        await service.upload_file_to_s3(
            "https://s3.example.com/presigned",
            b"%PDF",
            content_type="application/pdf",
        )

    call_kw = mock_inner.put.call_args.kwargs
    assert call_kw["headers"] == {"Content-Type": "application/pdf"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pipefy_client_create_presigned_url_delegates_to_attachment_service():
    attachment = AsyncMock()
    attachment.create_presigned_url = AsyncMock(
        return_value={"url": "https://s3/u", "download_url": "https://app/dl"}
    )
    client = PipefyClient.__new__(PipefyClient)
    client._attachment_service = attachment

    result = await client.create_presigned_url(
        "302398434",
        "doc.pdf",
        content_type="application/pdf",
        content_length=128,
    )

    attachment.create_presigned_url.assert_awaited_once_with(
        "302398434",
        "doc.pdf",
        content_type="application/pdf",
        content_length=128,
    )
    assert result == {"url": "https://s3/u", "download_url": "https://app/dl"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pipefy_client_upload_file_to_s3_delegates_to_attachment_service():
    attachment = AsyncMock()
    attachment.upload_file_to_s3 = AsyncMock(return_value={"status_code": 200})
    client = PipefyClient.__new__(PipefyClient)
    client._attachment_service = attachment

    result = await client.upload_file_to_s3(
        "https://s3/presigned",
        b"bytes",
        content_type="text/plain",
    )

    attachment.upload_file_to_s3.assert_awaited_once_with(
        "https://s3/presigned",
        b"bytes",
        content_type="text/plain",
    )
    assert result == {"status_code": 200}


@pytest.mark.unit
def test_pipefy_client_extract_storage_path_delegates_to_attachment_service():
    attachment = MagicMock()
    attachment.extract_storage_path = MagicMock(
        return_value="orgs/o/uploads/u/file.pdf",
    )
    client = PipefyClient.__new__(PipefyClient)
    client._attachment_service = attachment

    assert (
        client.extract_storage_path("https://bucket/file.pdf?x=1")
        == "orgs/o/uploads/u/file.pdf"
    )
    attachment.extract_storage_path.assert_called_once_with(
        "https://bucket/file.pdf?x=1",
    )
