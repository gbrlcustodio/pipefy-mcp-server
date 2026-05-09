"""Enforce `Discover via:` annotations on tools whose args depend on other tools.

Parses each tool module with ``ast`` to avoid importing the full server (the
monkey-patch in ``validation_envelope`` is side-effectful). For every audited
tool, asserts (a) the phrase ``"Discover via"`` appears in the docstring and
(b) each ``must_mention_tool`` substring is present, anchoring the hint to the
correct discovery path.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

AUDIT: list[tuple[str, str, list[str]]] = [
    # (tool name, module file under src/pipefy_mcp/tools/, must-mention tools)
    (
        "create_field_condition",
        "field_condition_tools.py",
        ["get_pipe", "get_phase_fields"],
    ),
    (
        "update_field_condition",
        "field_condition_tools.py",
        ["get_field_conditions", "get_phase_fields"],
    ),
    ("create_card_relation", "relation_tools.py", ["get_pipe_relations"]),
    ("create_pipe_relation", "relation_tools.py", ["search_pipes", "get_organization"]),
    ("get_pipe", "pipe_tools.py", ["search_pipes"]),
    ("get_card", "pipe_tools.py", ["find_cards"]),
    ("get_pipe_members", "pipe_tools.py", ["search_pipes"]),
    ("fill_card_phase_fields", "pipe_tools.py", ["get_phase_fields"]),
    ("update_card_field", "pipe_tools.py", ["get_phase_fields"]),
    ("move_card_to_phase", "pipe_tools.py", ["get_pipe"]),
    ("create_phase_field", "pipe_config_tools.py", ["get_pipe"]),
    ("update_phase_field", "pipe_config_tools.py", ["get_phase_fields"]),
    ("delete_phase_field", "pipe_config_tools.py", ["get_phase_fields"]),
    ("update_phase", "pipe_config_tools.py", ["get_pipe"]),
    ("create_table_field", "table_tools.py", ["search_tables"]),
    ("create_table_record", "table_tools.py", ["search_tables", "get_table"]),
    ("update_table_record", "table_tools.py", ["find_records"]),
    ("set_table_record_field_value", "table_tools.py", ["find_records", "get_table"]),
    ("create_ai_agent", "ai_agent_tools.py", ["search_pipes", "get_automation_events"]),
    ("update_ai_agent", "ai_agent_tools.py", ["get_ai_agents"]),
    (
        "validate_ai_agent_behaviors",
        "ai_agent_tools.py",
        ["search_pipes", "get_automation_events"],
    ),
    (
        "create_ai_automation",
        "ai_automation_tools.py",
        ["get_automation_events", "get_phase_fields"],
    ),
    (
        "update_ai_automation",
        "ai_automation_tools.py",
        ["get_ai_automations"],
    ),
    (
        "validate_ai_automation_prompt",
        "ai_automation_tools.py",
        ["get_phase_fields", "get_automation_events"],
    ),
    ("create_webhook", "webhook_tools.py", ["search_pipes"]),
    ("update_webhook", "webhook_tools.py", ["get_webhooks"]),
]

_TOOLS_DIR = pathlib.Path(__file__).parents[2] / "src" / "pipefy_mcp" / "tools"


def _collect_tool_docstrings(module_path: pathlib.Path) -> dict[str, str]:
    """Return ``{tool_name: docstring}`` for every @mcp.tool-decorated inner fn.

    Walks the whole AST — the decorator detection is intentionally tolerant
    so it finds both plain ``@mcp.tool(...)`` and bare ``@mcp.tool`` forms.
    """
    tree = ast.parse(module_path.read_text())
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if not _has_mcp_tool_decorator(node):
            continue
        docstring = ast.get_docstring(node) or ""
        found[node.name] = docstring
    return found


def _has_mcp_tool_decorator(node: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "mcp"
            and target.attr == "tool"
        ):
            return True
    return False


@pytest.fixture(scope="module")
def docstrings_by_module() -> dict[str, dict[str, str]]:
    cache: dict[str, dict[str, str]] = {}
    for _, module_filename, _ in AUDIT:
        if module_filename not in cache:
            cache[module_filename] = _collect_tool_docstrings(
                _TOOLS_DIR / module_filename
            )
    return cache


@pytest.mark.parametrize("tool_name,module_filename,must_mention", AUDIT)
def test_tool_docstring_has_discovery_hints(
    tool_name, module_filename, must_mention, docstrings_by_module
):
    module_docstrings = docstrings_by_module[module_filename]
    assert tool_name in module_docstrings, (
        f"Tool '{tool_name}' not found in {module_filename}. Update AUDIT if renamed."
    )
    docstring = module_docstrings[tool_name]
    assert "Discover via" in docstring, (
        f"Tool '{tool_name}' is missing a 'Discover via:' annotation. "
        f"Add one in the Args section for fields that depend on other tools."
    )
    for tool in must_mention:
        assert tool in docstring, (
            f"Tool '{tool_name}' docstring does not mention '{tool}'. "
            f"Add a 'Discover via: ... {tool} ...' line in the relevant Args entry."
        )
