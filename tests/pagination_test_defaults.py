"""Re-export pagination defaults from the canonical SDK test bundle."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SHARED = (
    Path(__file__).resolve().parent.parent
    / "packages"
    / "sdk"
    / "tests"
    / "_shared"
    / "pagination_test_defaults.py"
)

_spec = importlib.util.spec_from_file_location(
    "_pipefy_sdk_tests_pagination_defaults",
    _SHARED,
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

DEFAULT_FIRST = _mod.DEFAULT_FIRST
