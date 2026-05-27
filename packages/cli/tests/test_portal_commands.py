"""Tests for ``pipefy portal`` subcommands."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from _shared.fixture_ids import EXAMPLE_PIPE_REPO_ID

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
# Portal page subcommands (task 4.5 RED)
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
# Portal element subcommands (task 5.7 RED)
# ---------------------------------------------------------------------------

_ELEMENT_UUID = "el-uuid-1"
_FORMS_METADATA = {"name": "Request form"}
_FORMS_DATA_SOURCES = [{"repo_uuid": EXAMPLE_PIPE_REPO_ID}]

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
                "--element-uuid",
                _ELEMENT_UUID,
                "--interface-uuid",
                _PORTAL_UUID,
                "--page-uuid",
                _PAGE_UUID,
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == duplicated
    mock_client.duplicate_portal_element.assert_awaited_once_with(
        element_uuid=_ELEMENT_UUID,
        interface_uuid=_PORTAL_UUID,
        page_uuid=_PAGE_UUID,
    )


def test_portal_element_duplicate_missing_interface_uuid_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("portal-element-dup-no-iface")
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
                "--element-uuid",
                _ELEMENT_UUID,
                "--page-uuid",
                _PAGE_UUID,
                "--json",
            ],
        )
    assert result.exit_code == 2
    mock_client.duplicate_portal_element.assert_not_called()


def test_portal_element_duplicate_missing_page_uuid_exit_2(
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
                "--element-uuid",
                _ELEMENT_UUID,
                "--interface-uuid",
                _PORTAL_UUID,
                "--json",
            ],
        )
    assert result.exit_code == 2
    mock_client.duplicate_portal_element.assert_not_called()
