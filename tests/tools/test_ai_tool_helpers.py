"""Tests for AI tool helper functions (error enrichment, validation, payload builders)."""

import pytest
from gql.transport.exceptions import TransportQueryError

from pipefy_mcp.tools.ai_tool_helpers import (
    enrich_behavior_error,
    validate_behaviors_against_pipe,
)


def _make_behaviors(*specs):
    """Build minimal behavior dicts from (name, event_id, actionType) tuples."""
    result = []
    for name, event_id, action_type in specs:
        result.append(
            {
                "name": name,
                "event_id": event_id,
                "actionParams": {
                    "aiBehaviorParams": {
                        "instruction": "test",
                        "actionsAttributes": [
                            {
                                "name": f"{action_type} action",
                                "actionType": action_type,
                                "metadata": {},
                            },
                        ],
                    }
                },
            }
        )
    return result


@pytest.mark.unit
def test_enrich_includes_behavior_summary():
    behaviors = _make_behaviors(
        ("When created: classify", "card_created", "update_card"),
        ("When moved: notify", "card_moved", "move_card"),
    )
    exc = ValueError("Something went wrong")
    result = enrich_behavior_error(exc, behaviors)
    assert "Something went wrong" in result
    assert '[0] "When created: classify"' in result
    assert "event=card_created" in result
    assert "actions=[update_card]" in result
    assert '[1] "When moved: notify"' in result
    assert "event=card_moved" in result
    assert "actions=[move_card]" in result


@pytest.mark.unit
def test_enrich_adds_record_not_saved_hint():
    behaviors = _make_behaviors(("B1", "card_created", "update_card"))
    exc = TransportQueryError(
        "RECORD_NOT_SAVED", errors=[{"message": "RECORD_NOT_SAVED"}]
    )
    result = enrich_behavior_error(exc, behaviors)
    assert "RECORD_NOT_SAVED" in result
    assert "metadata is complete" in result
    assert "update_card needs pipeId" in result


@pytest.mark.unit
def test_enrich_adds_at_least_one_action_hint():
    behaviors = _make_behaviors(("B1", "card_created", "update_card"))
    exc = ValueError("must contain at least 1 action")
    result = enrich_behavior_error(exc, behaviors)
    assert "actionsAttributes" in result


@pytest.mark.unit
def test_enrich_no_hint_for_unknown_errors():
    behaviors = _make_behaviors(("B1", "card_created", "move_card"))
    exc = ValueError("timeout")
    result = enrich_behavior_error(exc, behaviors)
    assert "timeout" in result
    assert "Hints:" not in result


@pytest.mark.unit
def test_enrich_with_empty_behaviors():
    exc = ValueError("bad request")
    result = enrich_behavior_error(exc, [])
    assert "bad request" in result
    assert "Behaviors sent" not in result


@pytest.mark.unit
def test_enrich_strips_internal_api_diagnostic_markers():
    exc = ValueError(
        "Invalid prompt [code=INVALID_PROMPT] [correlation_id=secret-correlation-uuid]"
    )
    behaviors = _make_behaviors(("B1", "card_created", "update_card"))
    result = enrich_behavior_error(exc, behaviors)
    assert "Invalid prompt" in result
    assert "[code=" not in result
    assert "[correlation_id=" not in result
    assert "secret-correlation-uuid" not in result


@pytest.mark.unit
def test_enrich_only_diagnostic_markers_uses_generic_fallback():
    exc = ValueError(" [code=X] [correlation_id=Y]")
    behaviors = _make_behaviors(("B1", "card_created", "update_card"))
    result = enrich_behavior_error(exc, behaviors)
    assert "The AI behavior request failed" in result
    assert "[code=" not in result
    assert "Behaviors sent (1):" in result


@pytest.mark.unit
def test_enrich_handles_camel_case_behavior_keys():
    behaviors = [
        {
            "name": "CamelBehavior",
            "eventId": "field_updated",
            "actionParams": {
                "aiBehaviorParams": {
                    "instruction": "test",
                    "actionsAttributes": [
                        {
                            "name": "a",
                            "actionType": "create_connected_card",
                            "metadata": {},
                        },
                    ],
                }
            },
        }
    ]
    exc = ValueError("RECORD_NOT_SAVED: missing relation")
    result = enrich_behavior_error(exc, behaviors)
    assert '"CamelBehavior"' in result
    assert "event=field_updated" in result
    assert "actions=[create_connected_card]" in result


# --- validate_behaviors_against_pipe ---


def _update_card_behavior(field_id="100", pipe_id="1"):
    return {
        "name": "Fill fields",
        "event_id": "card_created",
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "go",
                "actionsAttributes": [
                    {
                        "name": "update",
                        "actionType": "update_card",
                        "metadata": {
                            "pipeId": pipe_id,
                            "fieldsAttributes": [
                                {
                                    "fieldId": field_id,
                                    "inputMode": "fill_with_ai",
                                    "value": "",
                                },
                            ],
                        },
                    },
                ],
            }
        },
    }


def _move_card_behavior(dest_phase_id="ph-1"):
    return {
        "name": "Move to done",
        "event_id": "card_moved",
        "eventParams": {"to_phase_id": "ph-start"},
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "go",
                "actionsAttributes": [
                    {
                        "name": "move",
                        "actionType": "move_card",
                        "metadata": {"destinationPhaseId": dest_phase_id},
                    },
                ],
            }
        },
    }


def _connected_card_behavior(target_pipe_id="child-pipe"):
    return {
        "name": "Create child",
        "event_id": "card_created",
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "go",
                "actionsAttributes": [
                    {
                        "name": "connect",
                        "actionType": "create_connected_card",
                        "metadata": {
                            "pipeId": target_pipe_id,
                            "fieldsAttributes": [
                                {
                                    "fieldId": "200",
                                    "inputMode": "fill_with_ai",
                                    "value": "",
                                },
                            ],
                        },
                    },
                ],
            }
        },
    }


def _create_table_record_behavior(field_id="tbl-field-999", table_id="tbl-1"):
    return {
        "name": "Insert table row",
        "event_id": "card_created",
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "go",
                "actionsAttributes": [
                    {
                        "name": "row",
                        "actionType": "create_table_record",
                        "metadata": {
                            "tableId": table_id,
                            "fieldsAttributes": [
                                {
                                    "fieldId": field_id,
                                    "inputMode": "fill_with_ai",
                                    "value": "",
                                },
                            ],
                        },
                    },
                ],
            }
        },
    }


def _send_email_template_behavior(
    *,
    email_template_id="tmpl-1",
    include_stray_fields_attributes=False,
):
    metadata = {
        "emailTemplateId": email_template_id,
        "allowTemplateModifications": True,
    }
    if include_stray_fields_attributes:
        metadata["fieldsAttributes"] = [
            {
                "fieldId": "999",
                "inputMode": "fill_with_ai",
                "value": "",
            },
        ]
    return {
        "name": "Send mail",
        "event_id": "card_created",
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "go",
                "actionsAttributes": [
                    {
                        "name": "email",
                        "actionType": "send_email_template",
                        "metadata": metadata,
                    },
                ],
            }
        },
    }


PIPE_FIELDS = {"100", "101", "102"}
PIPE_PHASES = {"ph-start", "ph-1", "ph-done"}
RELATED_PIPES = {"child-pipe", "sibling-pipe"}


@pytest.mark.unit
def test_validate_all_valid():
    problems, warnings = validate_behaviors_against_pipe(
        [_update_card_behavior(), _move_card_behavior()],
        pipe_id="1",
        pipe_field_ids=PIPE_FIELDS,
        pipe_phase_ids=PIPE_PHASES,
        related_pipe_ids=RELATED_PIPES,
    )
    assert problems == []
    assert warnings == []


@pytest.mark.unit
def test_validate_invalid_field_id():
    problems, warnings = validate_behaviors_against_pipe(
        [_update_card_behavior(field_id="999")],
        pipe_id="1",
        pipe_field_ids=PIPE_FIELDS,
        pipe_phase_ids=PIPE_PHASES,
        related_pipe_ids=RELATED_PIPES,
    )
    assert len(problems) == 1
    assert warnings == []
    assert '"999"' in problems[0]
    assert "not found in pipe fields" in problems[0]


@pytest.mark.unit
def test_validate_invalid_destination_phase():
    problems, warnings = validate_behaviors_against_pipe(
        [_move_card_behavior(dest_phase_id="ph-nonexistent")],
        pipe_id="1",
        pipe_field_ids=PIPE_FIELDS,
        pipe_phase_ids=PIPE_PHASES,
        related_pipe_ids=RELATED_PIPES,
    )
    assert warnings == []
    assert any(
        "ph-nonexistent" in p and "not found in pipe phases" in p for p in problems
    )


@pytest.mark.unit
def test_validate_invalid_event_params_to_phase_id():
    behavior = _move_card_behavior()
    behavior["eventParams"]["to_phase_id"] = "ph-ghost"
    problems, warnings = validate_behaviors_against_pipe(
        [behavior],
        pipe_id="1",
        pipe_field_ids=PIPE_FIELDS,
        pipe_phase_ids=PIPE_PHASES,
        related_pipe_ids=RELATED_PIPES,
    )
    assert warnings == []
    assert any(
        "ph-ghost" in p and "eventParams" in p and "toPhaseId" in p for p in problems
    )


@pytest.mark.unit
def test_validate_invalid_event_params_to_phase_id_camel_case():
    behavior = _move_card_behavior()
    del behavior["eventParams"]["to_phase_id"]
    behavior["eventParams"]["toPhaseId"] = "ph-ghost"
    problems, warnings = validate_behaviors_against_pipe(
        [behavior],
        pipe_id="1",
        pipe_field_ids=PIPE_FIELDS,
        pipe_phase_ids=PIPE_PHASES,
        related_pipe_ids=RELATED_PIPES,
    )
    assert warnings == []
    assert any("ph-ghost" in p for p in problems)


@pytest.mark.unit
def test_validate_create_connected_card_missing_relation():
    problems, warnings = validate_behaviors_against_pipe(
        [_connected_card_behavior(target_pipe_id="unrelated-pipe")],
        pipe_id="1",
        pipe_field_ids=PIPE_FIELDS,
        pipe_phase_ids=PIPE_PHASES,
        related_pipe_ids=RELATED_PIPES,
    )
    assert len(problems) == 1
    assert warnings == []
    assert "unrelated-pipe" in problems[0]
    assert "no relation" in problems[0]


@pytest.mark.unit
def test_validate_create_connected_card_skipped_when_relations_not_loaded():
    problems, warnings = validate_behaviors_against_pipe(
        [_connected_card_behavior(target_pipe_id="unrelated-pipe")],
        pipe_id="1",
        pipe_field_ids=PIPE_FIELDS,
        pipe_phase_ids=PIPE_PHASES,
        related_pipe_ids=None,
    )
    assert problems == []
    assert warnings == []


@pytest.mark.unit
def test_validate_create_table_record_skips_pipe_field_id_check():
    """Table field IDs are not validated against the source pipe."""
    problems, warnings = validate_behaviors_against_pipe(
        [_create_table_record_behavior(field_id="999")],
        pipe_id="1",
        pipe_field_ids=PIPE_FIELDS,
        pipe_phase_ids=PIPE_PHASES,
        related_pipe_ids=RELATED_PIPES,
    )
    assert problems == []
    assert len(warnings) == 1
    assert "create_table_record" in warnings[0]
    assert "get_table" in warnings[0] and "get_table_record" in warnings[0]


@pytest.mark.unit
def test_validate_send_email_template_skips_pipe_field_checks():
    """Email template actions do not cross-validate fieldIds against the pipe."""
    problems, warnings = validate_behaviors_against_pipe(
        [_send_email_template_behavior(include_stray_fields_attributes=True)],
        pipe_id="1",
        pipe_field_ids=PIPE_FIELDS,
        pipe_phase_ids=PIPE_PHASES,
        related_pipe_ids=RELATED_PIPES,
    )
    assert problems == []
    assert warnings == []
    assert not any("fieldsAttributes" in p for p in problems)


@pytest.mark.unit
def test_validate_create_connected_card_valid_relation():
    problems, warnings = validate_behaviors_against_pipe(
        [_connected_card_behavior(target_pipe_id="child-pipe")],
        pipe_id="1",
        pipe_field_ids=PIPE_FIELDS,
        pipe_phase_ids=PIPE_PHASES,
        related_pipe_ids=RELATED_PIPES,
    )
    assert problems == []
    assert warnings == []


@pytest.mark.unit
def test_validate_unknown_action_type_error():
    behavior = {
        "name": "Bad type",
        "event_id": "card_created",
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "go",
                "actionsAttributes": [
                    {"name": "x", "actionType": "update_card_field", "metadata": {}},
                ],
            }
        },
    }
    problems, warnings = validate_behaviors_against_pipe(
        [behavior],
        pipe_id="1",
        pipe_field_ids=PIPE_FIELDS,
        pipe_phase_ids=PIPE_PHASES,
        related_pipe_ids=RELATED_PIPES,
    )
    assert any("update_card_field" in p and "unknown" in p for p in problems)
    assert warnings == []


@pytest.mark.unit
def test_validate_unknown_action_type_warning_mode():
    behavior = {
        "name": "Bad type",
        "event_id": "card_created",
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "go",
                "actionsAttributes": [
                    {"name": "x", "actionType": "update_card_field", "metadata": {}},
                ],
            }
        },
    }
    problems, warnings = validate_behaviors_against_pipe(
        [behavior],
        pipe_id="1",
        pipe_field_ids=PIPE_FIELDS,
        pipe_phase_ids=PIPE_PHASES,
        related_pipe_ids=RELATED_PIPES,
        unknown_action_types="warning",
    )
    assert problems == []
    assert any("update_card_field" in w and "unknown" in w for w in warnings)


@pytest.mark.unit
def test_validate_unknown_action_type_ignore_mode():
    behavior = {
        "name": "Bad type",
        "event_id": "card_created",
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "go",
                "actionsAttributes": [
                    {"name": "x", "actionType": "update_card_field", "metadata": {}},
                ],
            }
        },
    }
    problems, warnings = validate_behaviors_against_pipe(
        [behavior],
        pipe_id="1",
        pipe_field_ids=PIPE_FIELDS,
        pipe_phase_ids=PIPE_PHASES,
        related_pipe_ids=RELATED_PIPES,
        unknown_action_types="ignore",
    )
    assert problems == []
    assert warnings == []


@pytest.mark.unit
def test_validate_empty_field_ids_skips_field_check():
    problems, warnings = validate_behaviors_against_pipe(
        [_update_card_behavior(field_id="any-id")],
        pipe_id="1",
        pipe_field_ids=set(),
        pipe_phase_ids=PIPE_PHASES,
        related_pipe_ids=RELATED_PIPES,
    )
    assert problems == []
    assert warnings == []


@pytest.mark.unit
def test_get_ai_agent_like_payload_passes_validation_helpers():
    """Round-trip style dict (camelCase eventParams) still validates cross-refs."""
    behavior = {
        "name": "Moved to review",
        "eventId": "card_moved",
        "eventParams": {"toPhaseId": "ph-start"},
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "Summarize.",
                "actionsAttributes": [
                    {
                        "name": "Move",
                        "actionType": "move_card",
                        "metadata": {"destinationPhaseId": "ph-1"},
                    },
                ],
            }
        },
    }
    problems, warnings = validate_behaviors_against_pipe(
        [behavior],
        pipe_id="1",
        pipe_field_ids=PIPE_FIELDS,
        pipe_phase_ids=PIPE_PHASES,
        related_pipe_ids=RELATED_PIPES,
    )
    assert problems == []
    assert warnings == []


# --- cross-pipe field validation ---


@pytest.mark.unit
def test_validate_cross_pipe_field_ids_valid():
    problems, warnings = validate_behaviors_against_pipe(
        [_connected_card_behavior(target_pipe_id="child-pipe")],
        pipe_id="1",
        pipe_field_ids=PIPE_FIELDS,
        pipe_phase_ids=PIPE_PHASES,
        related_pipe_ids=RELATED_PIPES,
        cross_pipe_field_ids={"child-pipe": {"200", "201"}},
    )
    assert problems == []


@pytest.mark.unit
def test_validate_cross_pipe_field_ids_invalid():
    problems, warnings = validate_behaviors_against_pipe(
        [_connected_card_behavior(target_pipe_id="child-pipe")],
        pipe_id="1",
        pipe_field_ids=PIPE_FIELDS,
        pipe_phase_ids=PIPE_PHASES,
        related_pipe_ids=RELATED_PIPES,
        cross_pipe_field_ids={"child-pipe": {"300", "301"}},
    )
    assert len(problems) == 1
    assert '"200"' in problems[0]
    assert "target pipe child-pipe fields" in problems[0]


@pytest.mark.unit
def test_validate_cross_pipe_not_in_map_skips_field_check():
    problems, warnings = validate_behaviors_against_pipe(
        [_connected_card_behavior(target_pipe_id="child-pipe")],
        pipe_id="1",
        pipe_field_ids=PIPE_FIELDS,
        pipe_phase_ids=PIPE_PHASES,
        related_pipe_ids=RELATED_PIPES,
        cross_pipe_field_ids={"other-pipe": {"200"}},
    )
    assert problems == []


# --- _summarize_behaviors malformed input ---


@pytest.mark.unit
def test_summarize_behaviors_malformed_non_dict():
    from pipefy_mcp.tools.ai_tool_helpers import _summarize_behaviors

    result = _summarize_behaviors(["not a dict", 42])
    assert "<malformed: str>" in result
    assert "<malformed: int>" in result


@pytest.mark.unit
def test_summarize_behaviors_action_params_as_string():
    from pipefy_mcp.tools.ai_tool_helpers import _summarize_behaviors

    result = _summarize_behaviors(
        [{"name": "Bad", "event_id": "x", "actionParams": "garbage"}]
    )
    assert '"Bad"' in result
    assert "actions=[none]" in result


@pytest.mark.unit
def test_summarize_behaviors_missing_action_params():
    from pipefy_mcp.tools.ai_tool_helpers import _summarize_behaviors

    result = _summarize_behaviors([{"name": "Bare", "event_id": "card_created"}])
    assert '"Bare"' in result
    assert "actions=[none]" in result


# --- _extract_pipe_id_from_behaviors ---


@pytest.mark.unit
def test_extract_pipe_id_from_update_card_behavior():
    from pipefy_mcp.tools.ai_agent_tools import _extract_pipe_id_from_behaviors

    behaviors = [_update_card_behavior(pipe_id="306996636")]
    assert _extract_pipe_id_from_behaviors(behaviors) == "306996636"


@pytest.mark.unit
def test_extract_pipe_id_returns_none_for_empty():
    from pipefy_mcp.tools.ai_agent_tools import _extract_pipe_id_from_behaviors

    assert _extract_pipe_id_from_behaviors([]) is None


@pytest.mark.unit
def test_extract_pipe_id_returns_none_for_malformed():
    from pipefy_mcp.tools.ai_agent_tools import _extract_pipe_id_from_behaviors

    assert _extract_pipe_id_from_behaviors([{"actionParams": "garbage"}]) is None


@pytest.mark.unit
def test_extract_pipe_id_from_move_card_behavior():
    from pipefy_mcp.tools.ai_agent_tools import _extract_pipe_id_from_behaviors

    # move_card doesn't have metadata.pipeId
    assert _extract_pipe_id_from_behaviors([_move_card_behavior()]) is None
