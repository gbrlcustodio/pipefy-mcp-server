"""Behaviour of the generated GraphQL input models and their shared base."""

from __future__ import annotations

import pytest
from _shared.fixture_ids import EXAMPLE_PIPE_ID
from pydantic import ValidationError

from pipefy_sdk.graphql_inputs import (
    COLORS_VALUES,
    ConditionExpressionInput,
    ConditionInput,
    CreateFieldConditionInput,
    CreatePhaseFieldInput,
    UpdateLabelInput,
    UpdatePhaseFieldInput,
    UpdatePipeInput,
    describe_input_rejection,
)
from pipefy_sdk.utils import normalize_field_condition_fields


class TestSerialization:
    def test_unset_fields_are_not_sent(self):
        payload = UpdatePipeInput(
            id=EXAMPLE_PIPE_ID, name="Onboarding"
        ).to_graphql_input()
        assert payload == {"id": EXAMPLE_PIPE_ID, "name": "Onboarding"}

    def test_explicit_none_is_indistinguishable_from_unset(self):
        """The documented limit: a field cannot be sent as an explicit null."""
        payload = UpdatePipeInput(id="1", name=None).to_graphql_input()
        assert "name" not in payload

    def test_nested_input_serializes_and_drops_its_own_unset_fields(self):
        payload = CreateFieldConditionInput(
            phaseId="9",
            condition=ConditionInput(
                expressions=[ConditionExpressionInput(field_address="123")]
            ),
        ).to_graphql_input()
        assert payload["condition"] == {"expressions": [{"field_address": "123"}]}


class TestIdIsNotCoerced:
    """`ID` accepts a string or an integer, and the SDK passes through both.

    ``createFieldCondition`` answers a string ``expressions_structure`` entry with
    an opaque 500, so coercing towards ``str`` would break it; ``update_pipe``
    takes either, so nothing gains from coercing the other way.
    """

    def test_integer_id_stays_an_integer(self):
        payload = UpdatePipeInput(id=int(EXAMPLE_PIPE_ID), name="x").to_graphql_input()
        assert payload["id"] == int(EXAMPLE_PIPE_ID)

    def test_string_id_stays_a_string(self):
        payload = UpdatePipeInput(id=EXAMPLE_PIPE_ID, name="x").to_graphql_input()
        assert payload["id"] == EXAMPLE_PIPE_ID

    def test_expressions_structure_keeps_its_integers(self):
        payload = ConditionInput(expressions_structure=[[0, 1]]).to_graphql_input()
        assert payload["expressions_structure"] == [[0, 1]]


class TestUnknownFields:
    def test_a_misspelled_field_is_rejected_by_name(self):
        with pytest.raises(ValidationError) as exc_info:
            UpdatePipeInput(id="1", nmae="Onboarding")
        assert describe_input_rejection(exc_info.value) == (
            "'nmae' is not an accepted field"
        )

    def test_a_misspelled_nested_field_is_reported_by_its_path(self):
        with pytest.raises(ValidationError) as exc_info:
            UpdatePipeInput(id="1", preferences={"findabl": True})
        assert describe_input_rejection(exc_info.value) == (
            "'preferences.findabl' is not an accepted field"
        )


class TestRequiredFields:
    """The schema requires several fields on an update that reads as partial."""

    def test_update_label_requires_name_and_color(self):
        with pytest.raises(ValidationError) as exc_info:
            UpdateLabelInput(id="1")
        assert "is required" in describe_input_rejection(exc_info.value)

    def test_update_phase_field_requires_label(self):
        with pytest.raises(ValidationError) as exc_info:
            UpdatePhaseFieldInput(id="prioridade")
        assert describe_input_rejection(exc_info.value) == "'label' is required"

    def test_create_phase_field_requires_phase_id_label_and_type(self):
        with pytest.raises(ValidationError):
            CreatePhaseFieldInput(label="Priority", type="select")


class TestSoftEnums:
    def test_a_value_outside_the_documented_set_is_still_sent(self):
        """A colour added server-side must work without an SDK release."""
        payload = UpdatePipeInput(id="1", color="chartreuse").to_graphql_input()
        assert payload["color"] == "chartreuse"

    def test_the_documented_values_are_exported(self):
        assert "blue" in COLORS_VALUES
        assert isinstance(COLORS_VALUES, tuple)


class TestRejectionMessages:
    def test_a_type_error_names_the_field_and_the_reason(self):
        with pytest.raises(ValidationError) as exc_info:
            CreatePhaseFieldInput(
                phase_id="9", label="Priority", type="select", index="soon"
            )
        message = describe_input_rejection(exc_info.value)
        assert message.startswith("'index' ")

    def test_the_offending_value_is_never_echoed(self):
        """A secret in the wrong field must not reach a transcript or shell log."""
        with pytest.raises(ValidationError) as exc_info:
            UpdatePipeInput(id="1", api_token="hunter2-super-secret")
        assert "hunter2" not in describe_input_rejection(exc_info.value)


class TestLegacyConditionShapes:
    """The models mirror the schema, so the shapes GraphQL coerces are repaired first.

    ``expressions_structure: [0]`` is legal on the wire — GraphQL coerces a bare
    value into a single-item list, and the API stores it as ``[["0"]]``. A model
    typed from ``[[ID]]`` refuses it, so ``normalize_field_condition_fields``
    runs before the input is parsed.
    """

    def test_a_flat_expressions_structure_is_rejected_by_the_raw_model(self):
        with pytest.raises(ValidationError):
            ConditionInput(expressions_structure=[0, 1])

    def test_the_repair_wraps_it_so_the_model_accepts_it(self):
        repaired = normalize_field_condition_fields(
            {
                "phaseId": "9",
                "condition": {"expressions": [], "expressions_structure": [0, 1]},
            }
        )
        assert repaired["condition"]["expressions_structure"] == [[0], [1]]
        model = CreateFieldConditionInput(**repaired)
        assert model.to_graphql_input()["condition"]["expressions_structure"] == [
            [0],
            [1],
        ]

    def test_the_repair_is_idempotent(self):
        """The service runs the same normalizers again on the serialized payload."""
        once = normalize_field_condition_fields(
            {
                "condition": {
                    "expressions": [{"id": "drop-me", "structure_id": "0"}],
                    "expressions_structure": ["0"],
                },
                "actions": [{"phaseFieldId": "1", "actionId": "hidden"}],
            }
        )
        assert normalize_field_condition_fields(once) == once

    def test_a_legacy_hidden_action_survives_the_repair(self):
        repaired = normalize_field_condition_fields(
            {"actions": [{"phaseFieldId": "1", "actionId": "hidden"}]}
        )
        assert repaired["actions"][0]["actionId"] == "hide"
