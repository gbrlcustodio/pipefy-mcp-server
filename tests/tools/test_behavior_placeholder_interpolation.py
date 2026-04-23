"""Tests for AI Agent behavior {{placeholder}} expansion."""

import copy

import pytest

from pipefy_mcp.tools.behavior_placeholder_interpolation import (
    expand_behavior_placeholders,
    expand_behaviors_placeholders,
    normalize_pipefy_ai_instruction_tokens,
)


def _minimal_behavior():
    return {
        "name": "B",
        "event_id": "card_created",
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "Hello",
                "actionsAttributes": [
                    {
                        "name": "U",
                        "actionType": "update_card",
                        "metadata": {
                            "pipeId": "1",
                            "fieldsAttributes": [
                                {
                                    "fieldId": "f1",
                                    "inputMode": "fill_with_ai",
                                    "value": "",
                                }
                            ],
                        },
                    }
                ],
            }
        },
    }


@pytest.mark.unit
def test_normalize_pipefy_tokens_adds_percent_prefix():
    text = (
        "Read {field:created_by} then %{field:already_ok} "
        "and {action:78164d3e-8b69-47dd-9dcc-56014f8a55c6} "
        "or %{action:11111111-1111-4111-8111-111111111111}"
    )
    out = normalize_pipefy_ai_instruction_tokens(text)
    assert "%{field:created_by}" in out
    assert "%{field:already_ok}" in out
    assert "%{action:78164d3e-8b69-47dd-9dcc-56014f8a55c6}" in out
    assert "%{action:11111111-1111-4111-8111-111111111111}" in out


@pytest.mark.unit
def test_normalize_promotes_bare_numeric_ids_to_field_namespace():
    """The AI Agent UI only renders chips for the ``field:`` / ``action:``
    namespaces. Callers often borrow the ``create_ai_automation`` style
    (bare ``%{<internal_id>}``) which stores fine via the API but the UI
    displays as plain text. We rewrite those variants to the canonical form."""
    text = "Read %{427911984} and {427911985} and %{field:427911986} and %{action:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa}"
    out = normalize_pipefy_ai_instruction_tokens(text)
    # Bare numeric variants promoted to %{field:<id>}
    assert "%{field:427911984}" in out
    assert "%{field:427911985}" in out
    # Already-canonical tokens left alone
    assert out.count("%{field:427911986}") == 1
    assert "%{action:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa}" in out
    # And the rewritten variants must not leak their old form
    assert "%{427911984}" not in out.replace("%{field:427911984}", "")
    assert "{427911985}" not in out.replace("%{field:427911985}", "")


@pytest.mark.unit
def test_normalize_leaves_non_numeric_bare_tokens_alone():
    """``{foo}`` without a namespace and with non-numeric content is left
    untouched — it may be a ``{{placeholder}}`` template param key or literal
    user text. Only numeric content is interpreted as a field internal_id."""
    text = "Keep {foo} and {bar:baz} as-is."
    out = normalize_pipefy_ai_instruction_tokens(text)
    assert out == text


@pytest.mark.unit
def test_normalize_empty_and_none_safe():
    assert normalize_pipefy_ai_instruction_tokens("") == ""


@pytest.mark.unit
def test_expand_normalizes_instruction_tokens_without_template_params():
    b = _minimal_behavior()
    b["actionParams"]["aiBehaviorParams"]["instruction"] = (
        "Use {field:my_slug} with {action:a81bdbec-0b0a-4ba9-b695-f4fe3f4f1f08}."
    )
    out = expand_behavior_placeholders(b)
    instr = out["actionParams"]["aiBehaviorParams"]["instruction"]
    assert "%{field:my_slug}" in instr
    assert "%{action:a81bdbec-0b0a-4ba9-b695-f4fe3f4f1f08}" in instr


@pytest.mark.unit
def test_expand_interpolates_metadata_and_instruction():
    b = _minimal_behavior()
    b["actionParams"]["aiBehaviorParams"]["instruction"] = "Fill {{field_id}}"
    b["actionParams"]["aiBehaviorParams"]["actionsAttributes"][0]["metadata"][
        "pipeId"
    ] = "{{pipe}}"
    b["actionParams"]["aiBehaviorParams"]["actionsAttributes"][0]["metadata"][
        "fieldsAttributes"
    ][0]["fieldId"] = "{{field_id}}"
    b["template_params"] = {"pipe": "99", "field_id": "427"}

    out = expand_behavior_placeholders(b)

    assert "template_params" not in out
    abp = out["actionParams"]["aiBehaviorParams"]
    assert abp["instruction"] == "Fill 427"
    meta = abp["actionsAttributes"][0]["metadata"]
    assert meta["pipeId"] == "99"
    assert meta["fieldsAttributes"][0]["fieldId"] == "427"


@pytest.mark.unit
def test_instruction_template_sets_instruction_then_interpolates():
    b = _minimal_behavior()
    del b["actionParams"]["aiBehaviorParams"]["instruction"]
    b["instruction_template"] = "Do {{what}}"
    b["placeholders"] = {"what": "summarize"}

    out = expand_behavior_placeholders(b)

    assert out["actionParams"]["aiBehaviorParams"]["instruction"] == "Do summarize"


@pytest.mark.unit
def test_missing_placeholder_key_raises():
    b = _minimal_behavior()
    b["actionParams"]["aiBehaviorParams"]["instruction"] = "{{missing}}"
    b["template_params"] = {"other": "x"}

    with pytest.raises(ValueError, match="Missing template parameter 'missing'"):
        expand_behavior_placeholders(b)


@pytest.mark.unit
def test_empty_template_params_with_placeholder_raises():
    b = _minimal_behavior()
    b["actionParams"]["aiBehaviorParams"]["instruction"] = "{{missing}}"
    b["template_params"] = {}

    with pytest.raises(ValueError, match="no template_params"):
        expand_behavior_placeholders(b)


@pytest.mark.unit
def test_placeholder_without_params_raises():
    b = _minimal_behavior()
    b["actionParams"]["aiBehaviorParams"]["instruction"] = "Has {{x}}"

    with pytest.raises(ValueError, match="no template_params"):
        expand_behavior_placeholders(b)


@pytest.mark.unit
def test_original_dict_not_mutated():
    b = _minimal_behavior()
    b["template_params"] = {"a": "1"}
    b["actionParams"]["aiBehaviorParams"]["instruction"] = "{{a}}"
    original = copy.deepcopy(b)

    expand_behavior_placeholders(b)

    assert b == original


@pytest.mark.unit
def test_expand_behaviors_placeholders_list():
    b1 = _minimal_behavior()
    b1["actionParams"]["aiBehaviorParams"]["instruction"] = "{{g}}"
    b1["template_params"] = {"g": "one"}
    b2 = _minimal_behavior()
    b2["actionParams"]["aiBehaviorParams"]["instruction"] = "{{g}}"
    b2["template_params"] = {"g": "two"}

    outs = expand_behaviors_placeholders([b1, b2])
    assert outs[0]["actionParams"]["aiBehaviorParams"]["instruction"] == "one"
    assert outs[1]["actionParams"]["aiBehaviorParams"]["instruction"] == "two"


@pytest.mark.unit
def test_placeholders_overrides_template_params_same_key():
    b = _minimal_behavior()
    b["actionParams"]["aiBehaviorParams"]["instruction"] = "{{k}}"
    b["template_params"] = {"k": "first"}
    b["placeholders"] = {"k": "second"}

    out = expand_behavior_placeholders(b)
    assert out["actionParams"]["aiBehaviorParams"]["instruction"] == "second"
