"""Pytest defaults for ``packages/sdk/tests``.

Pin the anyio backend to ``asyncio`` so ``@pytest.mark.anyio`` tests do not
attempt to load ``trio`` (which is not a project dependency). The repo-root
``tests/conftest.py`` defines the same fixture for the cross-package layer;
this mirror exists so the SDK suite passes when run in isolation
(``uv run pytest packages/sdk/tests``).
"""

from __future__ import annotations

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
