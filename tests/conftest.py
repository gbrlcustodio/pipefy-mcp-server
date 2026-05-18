"""Shared pytest configuration for the repo-root ``tests/`` tree.

Cross-package checks live here (for example ``test_parity.py``). Keep this
directory **without** ``__init__.py``: a root ``tests`` package would shadow
``packages/sdk/tests`` when pytest imports modules as ``tests.test_*``.
"""

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
