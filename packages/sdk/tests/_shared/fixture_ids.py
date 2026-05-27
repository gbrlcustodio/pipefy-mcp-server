"""Fictional organization and pipe identifiers for **unit tests only**.

Do not copy production org UUIDs, numeric org ids, or pipe repo ids into test code.
Live integration tests read real identifiers from repo-root ``.env`` (e.g.
``PIPEFY_PORTAL_ORG_UUID`` for portal SDK smoke — see ``docs/setup.md`` and
``.env.example``).
"""

from __future__ import annotations

EXAMPLE_NUMERIC_ORG_ID = "123456789"
EXAMPLE_ORG_UUID = "00000000-0000-4000-8000-000000000001"
EXAMPLE_OTHER_ORG_UUID = "00000000-0000-4000-8000-000000000002"
EXAMPLE_PIPE_REPO_ID = "987654321"
