#!/usr/bin/env python3
"""Validate MCP tool names and top-level ``pipefy`` CLI tokens referenced in skills/."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# Typer sub-apps registered on the root CLI (see packages/cli/src/pipefy_cli/main.py).
PIPEFY_CLI_ROOT_COMMANDS = frozenset(
    {
        "agent",
        "ai-automation",
        "attachment",
        "audit",
        "automation",
        "card",
        "email",
        "export",
        "field",
        "field-condition",
        "graphql",
        "introspect",
        "label",
        "member",
        "org",
        "phase",
        "pipe",
        "portal",
        "record",
        "relation",
        "report-org",
        "report-pipe",
        "table",
        "usage",
        "webhook",
    }
)

# ``pipefy`` used in prose (e.g. install instructions) — not a subcommand.
_SKIP_CLI_LINE_SUBSTRINGS = (
    "uvx --from",
    "uv tool install",
    "github.com",
    "pipefy-cli",
    "pipefy-mcp-server",
)

MCP_TOOL_CELL_RE = re.compile(
    r"^\|\s*`([a-z][a-z0-9_]*)`\s*\|",
    re.IGNORECASE,
)

PIPEFY_INVOCATION_RE = re.compile(
    r"(?<![A-Za-z0-9])pipefy\s+([a-z][a-z0-9-]*)\b",
)


def _tool_names_from_ast_value(node: ast.expr) -> frozenset[str]:
    """Extract string tool names from ``frozenset({...})`` or ``set({...})``."""
    if not isinstance(node, ast.Call):
        msg = "PIPEFY_TOOL_NAMES value must be a frozenset(...) or set(...) call"
        raise RuntimeError(msg)
    if not isinstance(node.func, ast.Name) or node.func.id not in ("frozenset", "set"):
        msg = "PIPEFY_TOOL_NAMES must be assigned from frozenset(...) or set(...)"
        raise RuntimeError(msg)
    if len(node.args) != 1:
        msg = "PIPEFY_TOOL_NAMES frozenset/set must have exactly one argument"
        raise RuntimeError(msg)
    arg0 = node.args[0]
    if not isinstance(arg0, ast.Set):
        msg = "PIPEFY_TOOL_NAMES argument must be a set literal {...}"
        raise RuntimeError(msg)
    names: list[str] = []
    for elt in arg0.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            names.append(elt.value)
        else:
            msg = f"PIPEFY_TOOL_NAMES entries must be string literals, got {ast.dump(elt)}"
            raise RuntimeError(msg)
    return frozenset(names)


def _load_pipefy_tool_names() -> frozenset[str]:
    registry_path = REPO_ROOT / "packages/mcp/src/pipefy_mcp/tools/registry.py"
    tree = ast.parse(registry_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "PIPEFY_TOOL_NAMES":
                return _tool_names_from_ast_value(node.value)
    msg = "PIPEFY_TOOL_NAMES assignment not found in registry.py"
    raise RuntimeError(msg)


def _iter_skill_files(skills_root: Path) -> list[Path]:
    return sorted(p for p in skills_root.rglob("SKILL.md") if p.is_file())


def _lint_file(path: Path, tool_names: frozenset[str]) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(REPO_ROOT)

    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("|") and "`" in stripped:
            m = MCP_TOOL_CELL_RE.match(stripped)
            if m:
                tool = m.group(1)
                headerish = (
                    "tool (mcp)" in stripped.lower()
                    or stripped.lower().startswith("|------------")
                )
                if not headerish and tool not in tool_names:
                    errors.append(f"{rel}:{line_no}: unknown MCP tool `{tool}`")

        if "pipefy" not in line.lower():
            continue
        if any(s in line for s in _SKIP_CLI_LINE_SUBSTRINGS):
            continue
        for m in PIPEFY_INVOCATION_RE.finditer(line):
            sub = m.group(1).lower()
            if sub == "pipefy":
                continue
            if sub not in PIPEFY_CLI_ROOT_COMMANDS:
                errors.append(
                    f"{rel}:{line_no}: unknown CLI subcommand `{sub}` "
                    f"(from `{m.group(0)}`)",
                )
    return errors


def main() -> int:
    """Lint all skills under ``skills/`` for MCP and CLI reference validity.

    Returns:
        0 if no issues, 1 otherwise.
    """
    skills_root = REPO_ROOT / "skills"
    if not skills_root.is_dir():
        print("No skills/ directory found.", file=sys.stderr)
        return 1

    tool_names = _load_pipefy_tool_names()
    all_errors: list[str] = []
    for skill_path in _iter_skill_files(skills_root):
        all_errors.extend(_lint_file(skill_path, tool_names))

    if all_errors:
        print("Skill reference validation FAILED:", file=sys.stderr)
        for err in all_errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print(
        f"Skill reference validation passed ({len(_iter_skill_files(skills_root))} file(s))."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
