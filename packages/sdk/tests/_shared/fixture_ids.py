"""Fictional Pipefy identifiers for unit tests and skill examples.

Do not copy production org UUIDs, numeric org ids, or pipe repo ids into test code.
Live integration tests read real identifiers from repo-root ``.env`` (e.g.
``PIPEFY_PORTAL_ORG_UUID`` for portal SDK smoke — see ``docs/config.md`` and
``.env.example``). Replace fictional field/pipe ids below with values from
``get_pipe`` / ``get_start_form_fields`` in live workflows.
"""

from __future__ import annotations

import itertools

_pipe_id_counter = itertools.count(900_000_400)
_field_id_counter = itertools.count(900_000_500)


def make_pipe_id() -> str:
    """Unique fictional pipe id per call (avoids coincidental-pass with shared constants)."""
    return str(next(_pipe_id_counter))


def make_field_id() -> str:
    """Unique fictional field internal id per call."""
    return str(next(_field_id_counter))


EXAMPLE_NUMERIC_ORG_ID = "123456789"
EXAMPLE_ORG_UUID = "00000000-0000-4000-8000-000000000001"
EXAMPLE_OTHER_ORG_UUID = "00000000-0000-4000-8000-000000000002"

EXAMPLE_PIPE_ID = "987654321"
EXAMPLE_PIPE_REPO_ID = EXAMPLE_PIPE_ID
EXAMPLE_PIPE_ID_2 = "900000301"

EXAMPLE_PHASE_ID = "900000201"

EXAMPLE_FIELD_INTERNAL_ID = "900000101"
EXAMPLE_FIELD_INTERNAL_ID_2 = "900000102"
EXAMPLE_FIELD_INTERNAL_ID_3 = "900000103"
EXAMPLE_FIELD_INTERNAL_ID_4 = "900000110"
EXAMPLE_FIELD_INTERNAL_ID_5 = "900000111"
EXAMPLE_FIELD_INTERNAL_ID_6 = "900000112"

EXAMPLE_FIELD_SLUG = "resumo_de_briefing_ia"
EXAMPLE_FIELD_SLUG_2 = "objetivo_da_demanda"
EXAMPLE_FIELD_SLUG_3 = "phase_field_slug"

EXAMPLE_FIELD_INTERNAL_IDS_BY_SLUG: dict[str, str] = {
    "company_name": EXAMPLE_FIELD_INTERNAL_ID_4,
    "email": EXAMPLE_FIELD_INTERNAL_ID_5,
    "summary_field": EXAMPLE_FIELD_INTERNAL_ID_2,
    "approval_status": EXAMPLE_FIELD_INTERNAL_ID_6,
}
