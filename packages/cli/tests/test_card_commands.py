"""Tests for ``pipefy card`` subcommands beyond ``get``."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from pipefy_sdk.exceptions import MalformedPipefyResponseError

from pipefy_cli.main import app


def test_card_list_minimal_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("list-cards")
    payload = {"cards": {"edges": []}}
    mock_client = MagicMock()
    mock_client.get_cards = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["card", "list", "--pipe", "303", "--json"],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == payload
    mock_client.get_cards.assert_awaited_once_with(
        "303",
        None,
        include_fields=False,
        first=None,
        after=None,
    )


def test_card_list_title_search_and_pagination(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("list-cards-2")
    payload = {"cards": {"edges": [{"node": {"id": "1"}}]}}
    mock_client = MagicMock()
    mock_client.get_cards = AsyncMock(return_value=payload)
    search = json.dumps({"label_ids": ["abc"], "include_done": True})
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "card",
                "list",
                "--pipe",
                "9",
                "--title",
                " Acme ",
                "--search",
                search,
                "--include-fields",
                "--first",
                "50",
                "--after",
                "cursor1",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    mock_client.get_cards.assert_awaited_once()
    args, kwargs = mock_client.get_cards.await_args
    assert args[0] == "9"
    assert args[1] == {"label_ids": ["abc"], "include_done": True, "title": "Acme"}
    assert kwargs == {
        "include_fields": True,
        "first": 50,
        "after": "cursor1",
    }


def test_card_list_first_out_of_range_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("list-bad-first")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["card", "list", "--pipe", "1", "--first", "501", "--json"],
        )
    assert result.exit_code == 2
    mock_client.get_cards.assert_not_called()


def test_card_find_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("find-cards")
    payload = {"findCards": {"edges": []}}
    mock_client = MagicMock()
    mock_client.find_cards = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "card",
                "find",
                "--pipe",
                "303",
                "--field",
                "status",
                "--value",
                "Open",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == payload
    mock_client.find_cards.assert_awaited_once_with(
        "303",
        "status",
        "Open",
        include_fields=False,
        first=None,
        after=None,
    )


def test_card_create_with_title_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("create-card")
    create_resp = {"createCard": {"card": {"id": "777", "title": "Hello"}}}
    mock_client = MagicMock()
    mock_client.create_card = AsyncMock(return_value=create_resp)
    mock_client.update_card = AsyncMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "card",
                "create",
                "303",
                "--fields",
                '{"field_x": "y"}',
                "--title",
                "Hello",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    mock_client.create_card.assert_awaited_once_with(
        "303", {"field_x": "y"}, title="Hello"
    )
    mock_client.update_card.assert_not_called()


def test_card_create_forwards_phase_id(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("create-card-phase")
    create_resp = {"createCard": {"card": {"id": "888"}}}
    mock_client = MagicMock()
    mock_client.create_card = AsyncMock(return_value=create_resp)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "card",
                "create",
                "303",
                "--phase-id",
                "phase_42",
                "--fields",
                '{"status": "Open"}',
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    mock_client.create_card.assert_awaited_once_with(
        "303",
        {"status": "Open"},
        phase_id="phase_42",
    )


def test_card_create_title_warning_skipped_when_create_card_null(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("create-card-null-response")
    mock_client = MagicMock()
    mock_client.create_card = AsyncMock(return_value={"createCard": None})
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["card", "create", "303", "--title", "Requested", "--json"],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    payload = json.loads(result.stdout)
    assert payload == {"createCard": None}
    assert "title_warning" not in payload


def test_card_create_title_warning_when_mismatch(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("create-card-title-warn")
    create_resp = {"createCard": {"card": {"id": "890", "title": "Derived from field"}}}
    mock_client = MagicMock()
    mock_client.create_card = AsyncMock(return_value=create_resp)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["card", "create", "303", "--title", "Requested", "--json"],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    payload = json.loads(result.stdout)
    assert "title_warning" in payload
    assert "Requested" in payload["title_warning"]


def test_card_create_phase_id_and_title(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("create-card-phase-title")
    create_resp = {"createCard": {"card": {"id": "889", "title": "Seed"}}}
    mock_client = MagicMock()
    mock_client.create_card = AsyncMock(return_value=create_resp)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "card",
                "create",
                "303",
                "--phase-id",
                "999",
                "--title",
                "Seed",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    mock_client.create_card.assert_awaited_once_with(
        "303", {}, phase_id="999", title="Seed"
    )


def test_card_create_title_failure_exit_1(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("create-card-fail-title")
    from pipefy_sdk.exceptions import PipefyError

    mock_client = MagicMock()
    mock_client.create_card = AsyncMock(side_effect=PipefyError("create failed"))
    mock_client.update_card = AsyncMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "card",
                "create",
                "303",
                "--title",
                "Hello",
                "--json",
            ],
        )
    assert result.exit_code == 1
    mock_client.create_card.assert_awaited_once_with("303", {}, title="Hello")
    mock_client.update_card.assert_not_called()


def test_card_create_invalid_fields_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("bad-json")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["card", "create", "303", "--fields", "not-json", "--json"],
        )
    assert result.exit_code == 2
    mock_client.create_card.assert_not_called()


def test_card_update_field_updates(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("upd-card")
    payload = {"updateCard": {"success": True}}
    mock_client = MagicMock()
    mock_client.update_card = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "card",
                "update",
                "501",
                "--field-updates",
                json.dumps([{"fieldId": "f1", "value": "v"}]),
                "--json",
            ],
        )
    assert result.exit_code == 0
    mock_client.update_card.assert_awaited_once()
    kwargs = mock_client.update_card.await_args.kwargs
    assert kwargs["field_updates"] == [{"fieldId": "f1", "value": "v"}]


def test_card_delete_with_yes(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("del-card")
    payload = {"deleteCard": {"success": True}}
    mock_client = MagicMock()
    mock_client.delete_card = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["card", "delete", "501", "--yes", "--json"],
        )
    assert result.exit_code == 0
    mock_client.delete_card.assert_awaited_once_with("501")


def test_card_move_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("move-card")
    payload = {"moveCardToPhase": {"card": {"id": "501"}}}
    mock_client = MagicMock()
    mock_client.move_card_to_phase = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["card", "move", "501", "--phase", "999", "--json"],
        )
    assert result.exit_code == 0
    mock_client.move_card_to_phase.assert_awaited_once_with("501", "999")


def test_card_fill_filters_editable_and_updates(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("fill-card")
    phase_fields = {
        "phase_id": "100",
        "phase_name": "Review",
        "fields": [
            {
                "id": "status",
                "label": "Status",
                "type": "select",
                "editable": True,
            },
            {
                "id": "readonly",
                "label": "RO",
                "type": "short_text",
                "editable": False,
            },
        ],
    }
    update_resp = {"updateFieldsValues": {"success": True}}
    mock_client = MagicMock()
    mock_client.get_phase_fields = AsyncMock(return_value=phase_fields)
    mock_client.update_card = AsyncMock(return_value=update_resp)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "card",
                "fill",
                "99",
                "--phase",
                "100",
                "--fields",
                '{"status": "done", "readonly": "nope"}',
                "--required-only",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == {
        **update_resp,
        "skipped_field_ids": ["readonly"],
    }
    mock_client.get_phase_fields.assert_awaited_once_with("100", True)
    mock_client.update_card.assert_awaited_once_with(
        "99",
        field_updates=[{"field_id": "status", "value": "done"}],
    )


def test_card_fill_missing_editable_key_counts_as_editable(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("fill-card-missing-editable")
    update_resp = {"updateFieldsValues": {"success": True}}
    mock_client = MagicMock()
    mock_client.get_phase_fields = AsyncMock(
        return_value={
            "phase_id": "100",
            "fields": [{"id": "status", "type": "short_text"}],
        }
    )
    mock_client.update_card = AsyncMock(return_value=update_resp)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "card",
                "fill",
                "99",
                "--phase",
                "100",
                "--fields",
                '{"status": "done"}',
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == update_resp
    mock_client.update_card.assert_awaited_once_with(
        "99",
        field_updates=[{"field_id": "status", "value": "done"}],
    )


def test_card_fill_invalid_fields_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("fill-card-bad-json")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "card",
                "fill",
                "99",
                "--phase",
                "100",
                "--fields",
                "not-json",
                "--json",
            ],
        )
    assert result.exit_code == 2
    mock_client.get_phase_fields.assert_not_called()
    mock_client.update_card.assert_not_called()


def test_card_fill_no_fields_when_input_empty(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("fill-card-empty")
    mock_client = MagicMock()
    mock_client.get_phase_fields = AsyncMock(
        return_value={
            "phase_id": "100",
            "fields": [{"id": "status", "editable": True}],
        }
    )
    mock_client.update_card = AsyncMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "card",
                "fill",
                "99",
                "--phase",
                "100",
                "--fields",
                "{}",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == {
        "success": True,
        "message": "No fields to update.",
    }
    mock_client.get_phase_fields.assert_not_called()
    mock_client.update_card.assert_not_called()


def test_card_fill_typo_reports_skipped_field_ids(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("fill-card-typo")
    mock_client = MagicMock()
    mock_client.get_phase_fields = AsyncMock(
        return_value={
            "phase_id": "100",
            "fields": [{"id": "status", "editable": True}],
        }
    )
    mock_client.update_card = AsyncMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "card",
                "fill",
                "99",
                "--phase",
                "100",
                "--fields",
                '{"stauts": "done"}',
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == {
        "success": True,
        "message": "No fields to update.",
        "skipped_field_ids": ["stauts"],
    }
    mock_client.update_card.assert_not_called()


def test_card_fill_no_fields_when_only_non_editable(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("fill-card-non-editable")
    mock_client = MagicMock()
    mock_client.get_phase_fields = AsyncMock(
        return_value={
            "phase_id": "100",
            "fields": [{"id": "readonly", "editable": False}],
        }
    )
    mock_client.update_card = AsyncMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            [
                "card",
                "fill",
                "99",
                "--phase",
                "100",
                "--fields",
                '{"readonly": "nope"}',
                "--json",
            ],
        )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert json.loads(result.stdout) == {
        "success": True,
        "message": "No fields to update.",
        "skipped_field_ids": ["readonly"],
    }
    mock_client.update_card.assert_not_called()


def test_card_comment_update_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("cmt-upd")
    mock_client = MagicMock()
    mock_client.update_comment = AsyncMock(return_value="c1")
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["card", "comment", "update", "c1", "New body", "--json"],
        )
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"comment_id": "c1"}
    mock_client.update_comment.assert_awaited_once_with("c1", "New body")


def test_card_comment_add_json(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("cmt-add")
    mock_client = MagicMock()
    mock_client.add_card_comment = AsyncMock(return_value="c1")
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["card", "comment", "add", "501", "Hello from CLI", "--json"],
        )
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"comment_id": "c1"}
    mock_client.add_card_comment.assert_awaited_once_with("501", "Hello from CLI")


def test_card_comment_add_malformed_response_exits_1_with_message(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("cmt-malformed")
    mock_client = MagicMock()
    mock_client.add_card_comment = AsyncMock(
        side_effect=MalformedPipefyResponseError(
            "Pipefy accepted createComment but returned no comment id. "
            "The change may already be applied, so read the card's comments "
            "before retrying."
        )
    )
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["card", "comment", "add", "501", "Hello from CLI"],
        )
    assert result.exit_code == 1
    assert "may already be applied" in result.stderr


def test_card_comment_add_validation_exit_2(
    runner, clean_pipefy_env, saved_cwd, oauth_env
):
    oauth_env("cmt-bad")
    mock_client = MagicMock()
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["card", "comment", "add", "501", ""],
        )
    assert result.exit_code == 2
    mock_client.add_card_comment.assert_not_called()


def test_card_comment_delete_yes(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("cmt-del")
    payload = {"deleteComment": {"success": True}}
    mock_client = MagicMock()
    mock_client.delete_comment = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["card", "comment", "delete", "42", "--yes", "--json"],
        )
    assert result.exit_code == 0
    mock_client.delete_comment.assert_awaited_once_with("42")


def test_card_get_include_fields(runner, clean_pipefy_env, saved_cwd, oauth_env):
    oauth_env("get-inc")
    payload = {"card": {"id": "1", "fields": []}}
    mock_client = MagicMock()
    mock_client.get_card = AsyncMock(return_value=payload)
    with patch(
        "pipefy_cli.commands._common.get_authenticated_client",
        return_value=mock_client,
    ):
        result = runner.invoke(
            app,
            ["card", "get", "1", "--include-fields", "--json"],
        )
    assert result.exit_code == 0
    mock_client.get_card.assert_awaited_once_with("1", include_fields=True)
