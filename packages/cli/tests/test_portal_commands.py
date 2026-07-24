"""Tests for ``pipefy portal`` subcommands."""

from __future__ import annotations

import json
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from _shared.fixture_ids import EXAMPLE_PIPE_REPO_ID
from pipefy_sdk import PipefyGraphQLError

from pipefy_cli.main import app

_PORTAL_LIST_NODE = {
    "id": "portal-uuid-1",
    "uuid": "portal-uuid-1",
    "name": "Main Portal",
    "visibility": "internal",
    "subType": "portal",
}

_PORTAL_DETAIL = {
    "id": "portal-uuid-1",
    "uuid": "portal-uuid-1",
    "name": "Main Portal",
    "visibility": "public",
    "published": True,
    "pages": [
        {
            "id": "page-1",
            "uuid": "page-1",
            "title": "Home",
            "elements": [
                {
                    "id": "el-1",
                    "uuid": "el-1",
                    "type": "forms",
                    "metadata": {"name": "Request form"},
                }
            ],
        }
    ],
    "subPortals": [{"id": "sub-1", "uuid": "sub-1", "name": "Sub Portal 1"}],
}


def test_portal_list_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("portal-list")
    payload = [_PORTAL_LIST_NODE]
    mock_client = MagicMock()
    mock_client.list_portals = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["portal", "list", "--organization-uuid", "org-123", "--json"],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == payload
    mock_client.list_portals.assert_awaited_once_with("org-123", search_term=None)


def test_portal_get_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("portal-get")
    mock_client = MagicMock()
    mock_client.get_portal = AsyncMock(return_value=_PORTAL_DETAIL)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["portal", "get", "portal-uuid-1", "--json"],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == _PORTAL_DETAIL
    mock_client.get_portal.assert_awaited_once_with("portal-uuid-1")


def test_portal_list_missing_org_uuid_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-list-missing-org")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["portal", "list", "--json"])
    assert result.exit_code == 2
    mock_client.list_portals.assert_not_called()


def test_portal_get_missing_uuid_exit_2(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("portal-get-missing-uuid")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["portal", "get", "--json"])
    assert result.exit_code == 2
    mock_client.get_portal.assert_not_called()


def test_portal_delete_without_yes_exit_1(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-del-no-yes")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, ["portal", "delete", "portal-uuid-1"])
    assert result.exit_code == 1
    mock_client.delete_portal.assert_not_called()


def test_portal_delete_with_yes_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("portal-del-yes")
    payload = {"deleteInterface": {"success": True}}
    mock_client = MagicMock()
    mock_client.delete_portal = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["portal", "delete", "portal-uuid-1", "--yes", "--json"],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == payload
    mock_client.delete_portal.assert_awaited_once_with("portal-uuid-1")


def test_portal_create_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("portal-create")
    payload = {
        "id": "portal-uuid-new",
        "uuid": "portal-uuid-new",
        "name": "Main Portal",
    }
    mock_client = MagicMock()
    mock_client.create_portal = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["portal", "create", "--organization-uuid", "org-123", "--json"],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == payload
    mock_client.create_portal.assert_awaited_once_with("org-123")


def test_portal_update_name_visibility_json(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-update")
    payload = {
        "id": "portal-uuid-1",
        "uuid": "portal-uuid-1",
        "name": "Renamed Portal",
        "visibility": "public",
    }
    mock_client = MagicMock()
    mock_client.update_portal = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "update",
                "portal-uuid-1",
                "--name",
                "Renamed Portal",
                "--visibility",
                "public",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == payload
    mock_client.update_portal.assert_awaited_once_with(
        "portal-uuid-1",
        name="Renamed Portal",
        visibility="public",
    )


def test_portal_update_no_attributes_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-upd-none")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["portal", "update", "portal-uuid-1", "--json"],
        )
    assert result.exit_code == 2
    mock_client.update_portal.assert_not_called()


def test_portal_update_blank_name_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-upd-blank-name")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["portal", "update", "portal-uuid-1", "--name", "   ", "--json"],
        )
    assert result.exit_code == 2
    mock_client.update_portal.assert_not_called()


# ---------------------------------------------------------------------------
# Portal page subcommands
# ---------------------------------------------------------------------------

_PORTAL_UUID = "portal-uuid-1"
_PAGE_UUID = "page-uuid-1"
_PAGE_UUID_2 = "page-uuid-2"
_PAGE_TITLE = "Portal Home"

_CREATED_PAGE = {
    "id": _PAGE_UUID,
    "uuid": _PAGE_UUID,
    "title": _PAGE_TITLE,
    "elements": [{"id": "el-1", "uuid": "el-1", "type": "text"}],
}

_PAGE_LAYOUT = {"rows": [{"columns": [{"width": 12}]}]}


def test_portal_page_create_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("portal-page-create")
    mock_client = MagicMock()
    mock_client.create_portal_page = AsyncMock(return_value=_CREATED_PAGE)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "page",
                "create",
                "--portal-uuid",
                _PORTAL_UUID,
                "--title",
                _PAGE_TITLE,
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == _CREATED_PAGE
    mock_client.create_portal_page.assert_awaited_once_with(
        _PORTAL_UUID,
        _PAGE_TITLE,
        description=None,
        index=None,
    )


def test_portal_page_create_with_optional_fields_json(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-page-create-opts")
    mock_client = MagicMock()
    mock_client.create_portal_page = AsyncMock(return_value=_CREATED_PAGE)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "page",
                "create",
                "--portal-uuid",
                _PORTAL_UUID,
                "--title",
                _PAGE_TITLE,
                "--description",
                "Landing copy",
                "--index",
                "1",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    mock_client.create_portal_page.assert_awaited_once_with(
        _PORTAL_UUID,
        _PAGE_TITLE,
        description="Landing copy",
        index=1,
    )


def test_portal_page_update_title_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("portal-page-update")
    payload = {**_CREATED_PAGE, "title": "Renamed Page"}
    mock_client = MagicMock()
    mock_client.update_portal_page = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "page",
                "update",
                _PORTAL_UUID,
                _PAGE_UUID,
                "--title",
                "Renamed Page",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == payload
    mock_client.update_portal_page.assert_awaited_once_with(
        _PORTAL_UUID,
        _PAGE_UUID,
        title="Renamed Page",
    )


def test_portal_page_update_no_attributes_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-page-upd-none")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "page",
                "update",
                _PORTAL_UUID,
                _PAGE_UUID,
                "--json",
            ],
        )
    assert result.exit_code == 2
    mock_client.update_portal_page.assert_not_called()


def test_portal_page_delete_without_yes_exit_1(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-page-del-no-yes")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["portal", "page", "delete", _PORTAL_UUID, _PAGE_UUID],
        )
    assert result.exit_code == 1
    mock_client.delete_portal_page.assert_not_called()


def test_portal_page_delete_with_yes_json(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-page-del-yes")
    payload = {"deletePage": {"success": True}}
    mock_client = MagicMock()
    mock_client.delete_portal_page = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "page",
                "delete",
                _PORTAL_UUID,
                _PAGE_UUID,
                "--yes",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == payload
    mock_client.delete_portal_page.assert_awaited_once_with(_PORTAL_UUID, _PAGE_UUID)


def test_portal_page_sort_comma_separated_page_ids_json(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-page-sort-csv")
    page_ids = [_PAGE_UUID_2, _PAGE_UUID]
    payload = {"sortPages": {"success": True}}
    mock_client = MagicMock()
    mock_client.sort_portal_pages = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "page",
                "sort",
                "--portal-uuid",
                _PORTAL_UUID,
                "--page-ids",
                f"{_PAGE_UUID_2},{_PAGE_UUID}",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == payload
    mock_client.sort_portal_pages.assert_awaited_once_with(_PORTAL_UUID, page_ids)


def test_portal_page_sort_ids_json_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("portal-page-sort-json")
    page_ids = [_PAGE_UUID_2, _PAGE_UUID]
    payload = {"sortPages": {"success": True}}
    mock_client = MagicMock()
    mock_client.sort_portal_pages = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "page",
                "sort",
                "--portal-uuid",
                _PORTAL_UUID,
                "--ids-json",
                json.dumps(page_ids),
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    mock_client.sort_portal_pages.assert_awaited_once_with(_PORTAL_UUID, page_ids)


def test_portal_page_sort_page_ids_csv_rejects_duplicate_ids(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-page-sort-dup-csv")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "page",
                "sort",
                "--portal-uuid",
                _PORTAL_UUID,
                "--page-ids",
                f"{_PAGE_UUID},{_PAGE_UUID}",
                "--json",
            ],
        )
    assert result.exit_code == 2
    mock_client.sort_portal_pages.assert_not_called()


def test_portal_page_sort_ids_json_rejects_duplicate_ids(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-page-sort-dup-json")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "page",
                "sort",
                "--portal-uuid",
                _PORTAL_UUID,
                "--ids-json",
                json.dumps([_PAGE_UUID, _PAGE_UUID]),
                "--json",
            ],
        )
    assert result.exit_code == 2
    mock_client.sort_portal_pages.assert_not_called()


def test_portal_page_create_rejects_negative_index(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-page-create-bad-index")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "page",
                "create",
                "--portal-uuid",
                _PORTAL_UUID,
                "--title",
                "Home",
                "--index",
                "-1",
                "--json",
            ],
        )
    assert result.exit_code == 2
    mock_client.create_portal_page.assert_not_called()


def test_portal_page_sort_page_ids_csv_rejects_invalid_items(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-page-sort-invalid-csv")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "page",
                "sort",
                "--portal-uuid",
                _PORTAL_UUID,
                "--page-ids",
                "0,-1,page-1",
                "--json",
            ],
        )
    assert result.exit_code == 2
    mock_client.sort_portal_pages.assert_not_called()


def test_portal_page_sort_ids_json_rejects_invalid_items(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-page-sort-invalid-json")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "page",
                "sort",
                "--portal-uuid",
                _PORTAL_UUID,
                "--ids-json",
                json.dumps([None, "   ", False]),
                "--json",
            ],
        )
    assert result.exit_code == 2
    mock_client.sort_portal_pages.assert_not_called()


def test_portal_page_sort_missing_page_ids_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-page-sort-missing")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["portal", "page", "sort", "--portal-uuid", _PORTAL_UUID, "--json"],
        )
    assert result.exit_code == 2
    mock_client.sort_portal_pages.assert_not_called()


def test_portal_page_layout_update_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("portal-page-layout")
    payload = {"updatePageLayout": {"success": True}}
    mock_client = MagicMock()
    mock_client.update_portal_page_layout = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "page",
                "layout",
                "update",
                "--page-id",
                _PAGE_UUID,
                "--layout",
                json.dumps(_PAGE_LAYOUT),
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == payload
    mock_client.update_portal_page_layout.assert_awaited_once_with(
        _PAGE_UUID, _PAGE_LAYOUT
    )


# ---------------------------------------------------------------------------
# Portal element subcommands
# ---------------------------------------------------------------------------

_ELEMENT_UUID = "el-uuid-1"
_FORMS_METADATA = {"name": "Request form"}
_FORMS_DATA_SOURCES = [{"repoId": EXAMPLE_PIPE_REPO_ID}]

_CREATED_ELEMENT = {
    "id": _ELEMENT_UUID,
    "uuid": _ELEMENT_UUID,
    "type": "forms",
    "metadata": _FORMS_METADATA,
}


def test_portal_element_create_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("portal-element-create")
    mock_client = MagicMock()
    mock_client.create_portal_element = AsyncMock(return_value=_CREATED_ELEMENT)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "element",
                "create",
                "--page-id",
                _PAGE_UUID,
                "--type",
                "forms",
                "--metadata",
                json.dumps(_FORMS_METADATA),
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == _CREATED_ELEMENT
    mock_client.create_portal_element.assert_awaited_once_with(
        _PAGE_UUID,
        type="forms",
        metadata=_FORMS_METADATA,
        data_sources=[],
    )


def test_portal_element_create_with_data_sources_json(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-element-create-ds")
    mock_client = MagicMock()
    mock_client.create_portal_element = AsyncMock(return_value=_CREATED_ELEMENT)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "element",
                "create",
                "--page-id",
                _PAGE_UUID,
                "--type",
                "forms",
                "--metadata",
                json.dumps(_FORMS_METADATA),
                "--data-sources",
                json.dumps(_FORMS_DATA_SOURCES),
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    mock_client.create_portal_element.assert_awaited_once_with(
        _PAGE_UUID,
        type="forms",
        metadata=_FORMS_METADATA,
        data_sources=_FORMS_DATA_SOURCES,
    )


def test_portal_element_create_rejects_invalid_metadata_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-element-create-bad-meta")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "element",
                "create",
                "--page-id",
                _PAGE_UUID,
                "--type",
                "forms",
                "--metadata",
                json.dumps({}),
                "--json",
            ],
        )
    assert result.exit_code == 2
    mock_client.create_portal_element.assert_not_called()


def test_portal_element_create_missing_metadata_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-element-create-no-meta")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "element",
                "create",
                "--page-id",
                _PAGE_UUID,
                "--type",
                "forms",
                "--json",
            ],
        )
    assert result.exit_code == 2
    mock_client.create_portal_element.assert_not_called()


def test_portal_element_update_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("portal-element-update")
    link_metadata = {
        "linkUrl": "https://example.com/pipefy",
        "linkName": "Open",
    }
    payload = {
        **_CREATED_ELEMENT,
        "type": "link",
        "metadata": link_metadata,
    }
    mock_client = MagicMock()
    mock_client.update_portal_element = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "element",
                "update",
                _ELEMENT_UUID,
                _PAGE_UUID,
                "--type",
                "link",
                "--metadata",
                json.dumps(link_metadata),
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == payload
    mock_client.update_portal_element.assert_awaited_once_with(
        _ELEMENT_UUID,
        _PAGE_UUID,
        type="link",
        metadata=link_metadata,
        data_sources=[],
    )


def test_portal_element_update_rejects_invalid_metadata_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-element-upd-bad-meta")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "element",
                "update",
                _ELEMENT_UUID,
                _PAGE_UUID,
                "--type",
                "link",
                "--metadata",
                json.dumps({}),
                "--json",
            ],
        )
    assert result.exit_code == 2
    mock_client.update_portal_element.assert_not_called()


def test_portal_element_delete_without_yes_exit_1(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-element-del-no-yes")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["portal", "element", "delete", _ELEMENT_UUID, _PAGE_UUID],
        )
    assert result.exit_code == 1
    mock_client.delete_portal_element.assert_not_called()


def test_portal_element_delete_with_yes_json(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-element-del-yes")
    payload = {"deleteElement": {"success": True}}
    mock_client = MagicMock()
    mock_client.delete_portal_element = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "element",
                "delete",
                _ELEMENT_UUID,
                _PAGE_UUID,
                "--yes",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == payload
    mock_client.delete_portal_element.assert_awaited_once_with(
        _ELEMENT_UUID, _PAGE_UUID
    )


def test_portal_element_duplicate_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("portal-element-dup")
    duplicated = {
        "id": "el-copy",
        "uuid": "el-copy",
        "type": "text",
        "metadata": {},
    }
    mock_client = MagicMock()
    mock_client.duplicate_portal_element = AsyncMock(return_value=duplicated)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "element",
                "duplicate",
                "--element-id",
                _ELEMENT_UUID,
                "--portal-uuid",
                _PORTAL_UUID,
                "--page-id",
                _PAGE_UUID,
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == duplicated
    mock_client.duplicate_portal_element.assert_awaited_once_with(
        element_id=_ELEMENT_UUID,
        portal_uuid=_PORTAL_UUID,
        page_id=_PAGE_UUID,
    )


def test_portal_element_duplicate_missing_portal_uuid_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-element-dup-no-portal")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "element",
                "duplicate",
                "--element-id",
                _ELEMENT_UUID,
                "--page-id",
                _PAGE_UUID,
                "--json",
            ],
        )
    assert result.exit_code == 2
    mock_client.duplicate_portal_element.assert_not_called()


def test_portal_element_duplicate_missing_page_id_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-element-dup-no-page")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "element",
                "duplicate",
                "--element-id",
                _ELEMENT_UUID,
                "--portal-uuid",
                _PORTAL_UUID,
                "--json",
            ],
        )
    assert result.exit_code == 2
    mock_client.duplicate_portal_element.assert_not_called()


# ---------------------------------------------------------------------------
# Portal sub-portal subcommands (task 6.5 RED — sub_portal_app in 6.6)
# ---------------------------------------------------------------------------

_MAIN_PORTAL_UUID = _PORTAL_UUID
_SUB_PORTAL_UUID = "sub-portal-uuid-1"
_FORMS_ELEMENT_ID = "el-forms-1"
_SUB_PORTAL_NAME = "Sub Portal 1"

_CREATED_SUB_PORTAL = {
    "id": _SUB_PORTAL_UUID,
    "uuid": _SUB_PORTAL_UUID,
    "name": _SUB_PORTAL_NAME,
}

_UPDATE_SUB_PORTAL_ELEMENT_RESULT = {"updateSubPortalElement": {"success": True}}
_DELETE_SUB_PORTAL_ELEMENT_RESULT = {"deleteSubPortalElement": {"success": True}}
_DELETE_SUB_PORTAL_RESULT = {"deleteSubPortalInterface": {"success": True}}


def _sub_portal_validation_stderr(result) -> str:
    return (result.stderr or result.stdout or "").lower()


def test_portal_sub_portal_create_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("portal-sub-portal-create")
    mock_client = MagicMock()
    mock_client.create_sub_portal = AsyncMock(return_value=_CREATED_SUB_PORTAL)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "sub-portal",
                "create",
                "--main-portal-uuid",
                _MAIN_PORTAL_UUID,
                "--name",
                _SUB_PORTAL_NAME,
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == _CREATED_SUB_PORTAL
    mock_client.create_sub_portal.assert_awaited_once_with(
        _MAIN_PORTAL_UUID,
        name=_SUB_PORTAL_NAME,
    )


def test_portal_sub_portal_create_rejects_blank_main_portal_uuid_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-sub-portal-create-blank-main")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "sub-portal",
                "create",
                "--main-portal-uuid",
                "   ",
                "--name",
                _SUB_PORTAL_NAME,
                "--json",
            ],
        )
    assert result.exit_code == 2
    assert "non-empty" in _sub_portal_validation_stderr(result)
    mock_client.create_sub_portal.assert_not_called()


def test_portal_sub_portal_attach_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("portal-sub-portal-attach")
    mock_client = MagicMock()
    mock_client.update_sub_portal_element = AsyncMock(
        return_value=_UPDATE_SUB_PORTAL_ELEMENT_RESULT
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "sub-portal",
                "attach",
                _MAIN_PORTAL_UUID,
                _FORMS_ELEMENT_ID,
                _SUB_PORTAL_UUID,
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == _UPDATE_SUB_PORTAL_ELEMENT_RESULT
    mock_client.update_sub_portal_element.assert_awaited_once_with(
        _MAIN_PORTAL_UUID,
        _FORMS_ELEMENT_ID,
        _SUB_PORTAL_UUID,
    )


def test_portal_sub_portal_attach_rejects_blank_portal_uuid_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-sub-portal-attach-blank-portal")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "sub-portal",
                "attach",
                "   ",
                _FORMS_ELEMENT_ID,
                _SUB_PORTAL_UUID,
                "--json",
            ],
        )
    assert result.exit_code == 2
    assert "non-empty" in _sub_portal_validation_stderr(result)
    mock_client.update_sub_portal_element.assert_not_called()


def test_portal_sub_portal_attach_rejects_blank_element_id_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-sub-portal-attach-blank-element")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "sub-portal",
                "attach",
                _MAIN_PORTAL_UUID,
                "   ",
                _SUB_PORTAL_UUID,
                "--json",
            ],
        )
    assert result.exit_code == 2
    assert "non-empty" in _sub_portal_validation_stderr(result)
    mock_client.update_sub_portal_element.assert_not_called()


def test_portal_sub_portal_attach_rejects_blank_sub_portal_uuid_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-sub-portal-attach-blank-sub")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "sub-portal",
                "attach",
                _MAIN_PORTAL_UUID,
                _FORMS_ELEMENT_ID,
                "   ",
                "--json",
            ],
        )
    assert result.exit_code == 2
    assert "non-empty" in _sub_portal_validation_stderr(result)
    mock_client.update_sub_portal_element.assert_not_called()


def test_portal_sub_portal_detach_without_yes_exit_1(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-sub-portal-detach-no-yes")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "sub-portal",
                "detach",
                _MAIN_PORTAL_UUID,
                _FORMS_ELEMENT_ID,
            ],
        )
    assert result.exit_code == 1
    mock_client.delete_sub_portal_element.assert_not_called()


def test_portal_sub_portal_detach_with_yes_json(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-sub-portal-detach-yes")
    mock_client = MagicMock()
    mock_client.delete_sub_portal_element = AsyncMock(
        return_value=_DELETE_SUB_PORTAL_ELEMENT_RESULT
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "sub-portal",
                "detach",
                _MAIN_PORTAL_UUID,
                _FORMS_ELEMENT_ID,
                "--yes",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == _DELETE_SUB_PORTAL_ELEMENT_RESULT
    mock_client.delete_sub_portal_element.assert_awaited_once_with(
        _MAIN_PORTAL_UUID,
        _FORMS_ELEMENT_ID,
    )


def test_portal_sub_portal_publish_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("portal-sub-portal-publish")
    mock_client = MagicMock()
    mock_client.publish_sub_portal = AsyncMock(
        return_value=_UPDATE_SUB_PORTAL_ELEMENT_RESULT
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "sub-portal",
                "publish",
                _MAIN_PORTAL_UUID,
                _FORMS_ELEMENT_ID,
                _SUB_PORTAL_UUID,
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == _UPDATE_SUB_PORTAL_ELEMENT_RESULT
    mock_client.publish_sub_portal.assert_awaited_once_with(
        _MAIN_PORTAL_UUID,
        _FORMS_ELEMENT_ID,
        _SUB_PORTAL_UUID,
    )


def test_portal_sub_portal_publish_rejects_blank_sub_portal_uuid_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-sub-portal-publish-blank-sub")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "sub-portal",
                "publish",
                _MAIN_PORTAL_UUID,
                _FORMS_ELEMENT_ID,
                "   ",
                "--json",
            ],
        )
    assert result.exit_code == 2
    assert "non-empty" in _sub_portal_validation_stderr(result)
    mock_client.publish_sub_portal.assert_not_called()


def test_portal_sub_portal_unpublish_json(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-sub-portal-unpublish")
    mock_client = MagicMock()
    mock_client.unpublish_sub_portal = AsyncMock(
        return_value=_UPDATE_SUB_PORTAL_ELEMENT_RESULT
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "sub-portal",
                "unpublish",
                _MAIN_PORTAL_UUID,
                _FORMS_ELEMENT_ID,
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == _UPDATE_SUB_PORTAL_ELEMENT_RESULT
    mock_client.unpublish_sub_portal.assert_awaited_once_with(
        _MAIN_PORTAL_UUID,
        _FORMS_ELEMENT_ID,
    )


def test_portal_sub_portal_unpublish_rejects_blank_portal_uuid_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-sub-portal-unpublish-blank-portal")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "sub-portal",
                "unpublish",
                "   ",
                _FORMS_ELEMENT_ID,
                "--json",
            ],
        )
    assert result.exit_code == 2
    assert "non-empty" in _sub_portal_validation_stderr(result)
    mock_client.unpublish_sub_portal.assert_not_called()


def test_portal_sub_portal_delete_without_yes_exit_1(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-sub-portal-del-no-yes")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["portal", "sub-portal", "delete", _SUB_PORTAL_UUID],
        )
    assert result.exit_code == 1
    mock_client.delete_sub_portal.assert_not_called()


def test_portal_sub_portal_delete_with_yes_json(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-sub-portal-del-yes")
    mock_client = MagicMock()
    mock_client.delete_sub_portal = AsyncMock(return_value=_DELETE_SUB_PORTAL_RESULT)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "portal",
                "sub-portal",
                "delete",
                _SUB_PORTAL_UUID,
                "--yes",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == _DELETE_SUB_PORTAL_RESULT
    mock_client.delete_sub_portal.assert_awaited_once_with(_SUB_PORTAL_UUID)


_BLANK_SUB_PORTAL_CLI_ID_CASES: list[tuple[str, Callable[[str], list[str]], str]] = [
    (
        "create-main-portal",
        lambda blank: [
            "portal",
            "sub-portal",
            "create",
            "--main-portal-uuid",
            blank,
            "--name",
            _SUB_PORTAL_NAME,
            "--json",
        ],
        "create_sub_portal",
    ),
    (
        "detach-portal",
        lambda blank: [
            "portal",
            "sub-portal",
            "detach",
            blank,
            _FORMS_ELEMENT_ID,
            "--yes",
            "--json",
        ],
        "delete_sub_portal_element",
    ),
    (
        "detach-element",
        lambda blank: [
            "portal",
            "sub-portal",
            "detach",
            _MAIN_PORTAL_UUID,
            blank,
            "--yes",
            "--json",
        ],
        "delete_sub_portal_element",
    ),
    (
        "publish-portal",
        lambda blank: [
            "portal",
            "sub-portal",
            "publish",
            blank,
            _FORMS_ELEMENT_ID,
            _SUB_PORTAL_UUID,
            "--json",
        ],
        "publish_sub_portal",
    ),
    (
        "publish-element",
        lambda blank: [
            "portal",
            "sub-portal",
            "publish",
            _MAIN_PORTAL_UUID,
            blank,
            _SUB_PORTAL_UUID,
            "--json",
        ],
        "publish_sub_portal",
    ),
    (
        "unpublish-element",
        lambda blank: [
            "portal",
            "sub-portal",
            "unpublish",
            _MAIN_PORTAL_UUID,
            blank,
            "--json",
        ],
        "unpublish_sub_portal",
    ),
    (
        "delete-sub-portal",
        lambda blank: [
            "portal",
            "sub-portal",
            "delete",
            blank,
            "--yes",
            "--json",
        ],
        "delete_sub_portal",
    ),
]


@pytest.mark.parametrize("blank_id", ["", "   "])
@pytest.mark.parametrize(
    ("case_id", "build_args", "client_method"),
    _BLANK_SUB_PORTAL_CLI_ID_CASES,
    ids=[case[0] for case in _BLANK_SUB_PORTAL_CLI_ID_CASES],
)
def test_portal_sub_portal_rejects_blank_ids_exit_2(
    runner,
    clean_pipefy_env,
    saved_cwd,
    oauth_env,
    blank_id: str,
    case_id: str,
    build_args: Callable[[str], list[str]],
    client_method: str,
):
    oauth_env(f"portal-sub-portal-blank-{case_id}-{blank_id.strip() or 'empty'}")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(app, build_args(blank_id))
    assert result.exit_code == 2
    assert "non-empty" in _sub_portal_validation_stderr(result)
    getattr(mock_client, client_method).assert_not_called()


def test_portal_sub_portal_detach_graphql_error_exits_1(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    """A non-permission GraphQL error on an internal-API portal command exits 1.

    This path used to arrive as a ValueError (the ``[code=...]`` envelope) and
    exit 2, the usage-error code. It now raises PipefyGraphQLError and exits 1,
    aligned with public-API command failures. Permission errors still exit 2 via
    PortalPermissionError, unchanged.
    """
    oauth_env("portal-sub-detach-error")
    mock_client = MagicMock()
    mock_client.delete_sub_portal_element = AsyncMock(
        side_effect=PipefyGraphQLError(
            [{"message": "Something went wrong on the server"}]
        )
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["portal", "sub-portal", "detach", "portal-uuid-1", "element-1", "--yes"],
        )
    assert result.exit_code == 1, result.stdout + (result.stderr or "")
    mock_client.delete_sub_portal_element.assert_awaited_once_with(
        "portal-uuid-1", "element-1"
    )
