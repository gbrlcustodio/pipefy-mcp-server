"""Tests for the data_source_ids membership check in validate_ai_agent_behaviors_sdk."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from _shared.ai_agent_test_payloads import minimal_behavior_dict
from _shared.fixture_ids import EXAMPLE_PIPE_ID

from pipefy_sdk.ai_preflight import (
    _collect_configured_data_source_ids,
    _data_source_membership_warnings,
    validate_ai_agent_behaviors_sdk,
)

PIPE_UUID = "pipe-uuid-1"


CLEAN_FIELD_ID = "900000001"


def _behavior_with_data_sources(ids: list[str], *, snake: bool = False) -> dict:
    behavior = minimal_behavior_dict()
    key = "data_source_ids" if snake else "dataSourceIds"
    behavior["actionParams"]["aiBehaviorParams"][key] = ids
    return behavior


def _clean_behavior_with_data_sources(ids: list[str]) -> dict:
    """Behavior whose action targets the source pipe and a field present in context."""
    behavior = minimal_behavior_dict(pipe_id=EXAMPLE_PIPE_ID, field_id=CLEAN_FIELD_ID)
    behavior["actionParams"]["aiBehaviorParams"]["dataSourceIds"] = ids
    return behavior


class TestCollectConfiguredDataSourceIds:
    def test_unions_agent_and_behavior_level(self):
        behaviors = [
            _behavior_with_data_sources(["kb-b1"]),
            _behavior_with_data_sources(["kb-b2"], snake=True),
        ]
        result = _collect_configured_data_source_ids(behaviors, ["kb-a1", "kb-b1"])
        assert result == {"kb-a1", "kb-b1", "kb-b2"}

    def test_ignores_blank_ids_and_strips_padding(self):
        behaviors = [_behavior_with_data_sources(["  ", " kb-x "])]
        result = _collect_configured_data_source_ids(behaviors, ["", "   ", " kb-a "])
        assert result == {"kb-x", "kb-a"}

    def test_empty_when_none_configured(self):
        result = _collect_configured_data_source_ids([minimal_behavior_dict()], None)
        assert result == set()


class TestDataSourceMembershipWarnings:
    @pytest.mark.asyncio
    async def test_missing_id_warns(self):
        client = AsyncMock()
        client.get_pipe = AsyncMock(return_value={"pipe": {"uuid": PIPE_UUID}})
        client.get_ai_knowledge_bases = AsyncMock(return_value=[{"id": "kb-known"}])

        warnings = await _data_source_membership_warnings(
            client, EXAMPLE_PIPE_ID, {"kb-known", "kb-missing"}
        )

        assert len(warnings) == 1
        assert "kb-missing" in warnings[0]
        client.get_ai_knowledge_bases.assert_awaited_once_with(PIPE_UUID)

    @pytest.mark.asyncio
    async def test_all_known_no_warning(self):
        client = AsyncMock()
        client.get_pipe = AsyncMock(return_value={"pipe": {"uuid": PIPE_UUID}})
        client.get_ai_knowledge_bases = AsyncMock(
            return_value=[{"id": "kb-1"}, {"id": "kb-2"}]
        )

        warnings = await _data_source_membership_warnings(
            client, EXAMPLE_PIPE_ID, {"kb-1", "kb-2"}
        )

        assert warnings == []

    @pytest.mark.asyncio
    async def test_kb_list_failure_yields_single_warning(self):
        client = AsyncMock()
        client.get_pipe = AsyncMock(return_value={"pipe": {"uuid": PIPE_UUID}})
        client.get_ai_knowledge_bases = AsyncMock(
            side_effect=RuntimeError("permission denied")
        )

        warnings = await _data_source_membership_warnings(
            client, EXAMPLE_PIPE_ID, {"kb-1", "kb-2", "kb-3"}
        )

        assert len(warnings) == 1
        assert "probe failed" in warnings[0]

    @pytest.mark.asyncio
    async def test_pipe_fetch_failure_yields_single_warning(self):
        client = AsyncMock()
        client.get_pipe = AsyncMock(side_effect=RuntimeError("boom"))

        warnings = await _data_source_membership_warnings(
            client, EXAMPLE_PIPE_ID, {"kb-1"}
        )

        assert len(warnings) == 1
        assert "failed to load" in warnings[0]

    @pytest.mark.asyncio
    async def test_missing_uuid_yields_single_warning(self):
        client = AsyncMock()
        client.get_pipe = AsyncMock(return_value={"pipe": {}})

        warnings = await _data_source_membership_warnings(
            client, EXAMPLE_PIPE_ID, {"kb-1"}
        )

        assert len(warnings) == 1
        assert "no uuid" in warnings[0]


def _context_client(*, knowledge_bases) -> AsyncMock:
    """A client stubbed for the full validate flow with one known field in context."""
    client = AsyncMock()
    client.get_pipe = AsyncMock(
        return_value={
            "pipe": {
                "uuid": PIPE_UUID,
                "phases": [],
                "start_form_fields": [
                    {"id": "clean_slug", "internal_id": CLEAN_FIELD_ID}
                ],
            }
        }
    )
    client.get_pipe_relations = AsyncMock(return_value={"children": [], "parents": []})
    client.get_phase_fields = AsyncMock(return_value={"fields": []})
    client.get_ai_knowledge_bases = AsyncMock(return_value=knowledge_bases)
    return client


class TestValidateFlowWithDataSources:
    @pytest.mark.asyncio
    async def test_unknown_id_is_warning_not_problem(self):
        client = _context_client(knowledge_bases=[{"id": "kb-known"}])
        behavior = _clean_behavior_with_data_sources(["kb-known"])

        result = await validate_ai_agent_behaviors_sdk(
            client,
            EXAMPLE_PIPE_ID,
            [behavior],
            data_source_ids=["kb-agent-missing"],
        )

        assert result["valid"] is True
        assert any("kb-agent-missing" in w for w in result["warnings"])
        assert not any("kb-known" in w for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_no_data_sources_skips_kb_probe(self):
        client = _context_client(knowledge_bases=[{"id": "kb-known"}])

        result = await validate_ai_agent_behaviors_sdk(
            client,
            EXAMPLE_PIPE_ID,
            [minimal_behavior_dict(pipe_id=EXAMPLE_PIPE_ID, field_id=CLEAN_FIELD_ID)],
        )

        assert result["valid"] is True
        client.get_ai_knowledge_bases.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_probe_single_warning_valid_stays_true(self):
        client = _context_client(knowledge_bases=[])
        client.get_ai_knowledge_bases = AsyncMock(side_effect=RuntimeError("denied"))
        behavior = _clean_behavior_with_data_sources(["kb-b"])

        result = await validate_ai_agent_behaviors_sdk(
            client, EXAMPLE_PIPE_ID, [behavior], data_source_ids=["kb-a"]
        )

        assert result["valid"] is True
        probe_warnings = [w for w in result["warnings"] if "probe failed" in w]
        assert len(probe_warnings) == 1
