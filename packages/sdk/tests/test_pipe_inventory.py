"""Unit tests for get_pipe inventory normalization."""

from __future__ import annotations

import pytest

from pipefy_sdk.pipe_inventory import enrich_pipe_get_pipe_inventory


@pytest.mark.unit
def test_enrich_pipe_splits_start_form_from_phases():
    pipe = {
        "id": "10",
        "startFormPhaseId": "100",
        "phases": [
            {"id": "100", "name": "Start", "cards_count": 3},
            {"id": "200", "name": "Doing", "cards_count": 7},
        ],
    }
    enriched = enrich_pipe_get_pipe_inventory(pipe)
    assert enriched["start_form_phase"] == {
        "id": "100",
        "name": "Start",
        "cards_count": 3,
    }
    assert enriched["phases"] == [{"id": "200", "name": "Doing", "cards_count": 7}]


@pytest.mark.unit
def test_enrich_pipe_uses_fetched_start_form_when_absent_from_phases():
    pipe = {
        "id": "10",
        "startFormPhaseId": "100",
        "phases": [{"id": "200", "name": "Doing", "cards_count": 1}],
    }
    enriched = enrich_pipe_get_pipe_inventory(
        pipe,
        start_form_phase_row={"id": "100", "name": "Start", "cards_count": 0},
    )
    assert enriched["start_form_phase"]["cards_count"] == 0
    assert len(enriched["phases"]) == 1


@pytest.mark.unit
def test_enrich_pipe_without_start_form_id_leaves_phases_only():
    pipe = {
        "id": "10",
        "phases": [{"id": "200", "name": "Doing", "cards_count": 2}],
    }
    enriched = enrich_pipe_get_pipe_inventory(pipe)
    assert "start_form_phase" not in enriched
    assert enriched["phases"][0]["cards_count"] == 2


@pytest.mark.unit
def test_enrich_pipe_raises_when_workflow_phase_missing_cards_count():
    pipe = {"startFormPhaseId": "100", "phases": [{"id": "200", "name": "Doing"}]}
    with pytest.raises(ValueError, match="cards_count"):
        enrich_pipe_get_pipe_inventory(
            pipe,
            start_form_phase_row={"id": "100", "name": "Start", "cards_count": 0},
        )
