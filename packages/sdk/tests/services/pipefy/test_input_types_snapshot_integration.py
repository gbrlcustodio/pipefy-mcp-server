"""Live check that the committed input-type snapshot still matches the API.

This is the half of the drift guard CI cannot run: `generate_graphql_inputs.py
check` proves the models match the snapshot, and only a live introspection can
prove the snapshot still matches Pipefy. Requires valid Pipefy credentials
(e.g. `.env` with PIPEFY_*) and skips without them.

Run locally:
    uv run pytest packages/sdk/tests/services/pipefy/test_input_types_snapshot_integration.py -m integration -v
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from _shared.live_settings import (
    live_pipefy_settings,
    live_resolved_auth,
    require_live_creds,
)

from pipefy_sdk.graphql_executor import AuthenticatedExecutor, GraphQLEndpoint
from pipefy_sdk.services.schema_introspection_service import (
    SchemaIntrospectionService,
)

_SCRIPT = Path(__file__).resolve().parents[5] / "scripts" / "generate_graphql_inputs.py"


def _load_generator():
    """Load the generator lazily, so collection never depends on the script."""
    spec = importlib.util.spec_from_file_location("generate_graphql_inputs", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.integration
@pytest.mark.asyncio
async def test_input_types_snapshot_matches_live():
    """The snapshot is what the live schema says today, field for field.

    A failure means the API moved. Rerun
    ``scripts/generate_graphql_inputs.py snapshot`` and then ``generate``, and
    review the diff: a field that became required, or a type that changed, is a
    behaviour change for every caller of the method that takes it.
    """
    require_live_creds()
    generator = _load_generator()
    settings = live_pipefy_settings()
    endpoint = GraphQLEndpoint(
        url=settings.graphql_url,
        cache_schema=settings.gql_reuse_fetched_graphql_schema,
    )
    executor = AuthenticatedExecutor(endpoint=endpoint, auth=live_resolved_auth())
    service = SchemaIntrospectionService(executor=executor)
    result = await service.execute_graphql(generator.INTROSPECTION_QUERY)
    assert "__schema" in result, result

    live = generator.build_snapshot(result["__schema"]["types"])
    committed = json.loads(generator.SNAPSHOT_PATH.read_text())
    assert live == committed
