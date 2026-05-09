"""Re-export AI agent test payloads from the canonical SDK test bundle."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SHARED = (
    Path(__file__).resolve().parent.parent
    / "packages"
    / "sdk"
    / "tests"
    / "_shared"
    / "ai_agent_test_payloads.py"
)

_spec = importlib.util.spec_from_file_location(
    "_pipefy_sdk_tests_ai_agent_payloads",
    _SHARED,
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

behavior_with_action = _mod.behavior_with_action
minimal_behavior_dict = _mod.minimal_behavior_dict
mock_agent_with_behaviors = _mod.mock_agent_with_behaviors
mock_api_behavior_response = _mod.mock_api_behavior_response
mock_api_behavior_response_send_email_template = (
    _mod.mock_api_behavior_response_send_email_template
)
