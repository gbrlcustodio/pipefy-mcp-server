"""CI parity audit: MCP tool registry vs ``docs/parity.md`` and Typer CLI surface."""

from __future__ import annotations

import re
from pathlib import Path

import click
import pytest
from pipefy_cli.main import app as cli_app
from pipefy_mcp.tools.registry import PIPEFY_TOOL_NAMES
from typer.main import get_command

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PARITY_MD = _REPO_ROOT / "docs" / "parity.md"

_ROW_RE = re.compile(
    r"^\|\s*`([^`]+)`\s*\|\s*(.*?)\s*\|\s*(shipped|deferred|pending|N/A)\s*\|",
    re.IGNORECASE,
)
_PIPEFY_CMD_RE = re.compile(r"`(pipefy[^`]*)`")


def _parse_parity_rows(markdown):
    """Map MCP tool name -> (status_lower, list of ``pipefy ...`` strings from the CLI column)."""
    out = {}
    for line in markdown.splitlines():
        m = _ROW_RE.match(line.strip())
        if not m:
            continue
        tool, cli_cell, status = m.group(1), m.group(2), m.group(3).lower()
        specs = [s.strip() for s in _PIPEFY_CMD_RE.findall(cli_cell)]
        out[tool] = (status, specs)
    return out


def _tokens_before_first_flag(pipefy_tail):
    parts = pipefy_tail.strip().split()
    tokens = []
    for p in parts:
        if p.startswith("-"):
            break
        tokens.append(p)
    return tokens


def _command_path_exists(root, tokens):
    current = root
    for name in tokens:
        if not isinstance(current, click.Group):
            return False
        if name not in current.commands:
            return False
        current = current.commands[name]
    return True


def _click_root():
    cmd = get_command(cli_app)
    assert isinstance(cmd, click.Group)
    return cmd


def test_parity_matrix_covers_registry_and_cli_paths_exist():
    """Every MCP tool appears in ``docs/parity.md`` with a valid status; shipped rows resolve in Typer."""
    text = _PARITY_MD.read_text(encoding="utf-8")
    rows = _parse_parity_rows(text)

    missing_in_doc = sorted(PIPEFY_TOOL_NAMES - rows.keys())
    assert not missing_in_doc, (
        "MCP tools missing from docs/parity.md matrix: "
        + ", ".join(missing_in_doc)
        + ". Add a row for each tool in the same change set as registry edits."
    )

    extra_in_doc = sorted(rows.keys() - PIPEFY_TOOL_NAMES)
    assert not extra_in_doc, (
        "docs/parity.md lists unknown MCP tools (not in PIPEFY_TOOL_NAMES): "
        + ", ".join(extra_in_doc)
        + ". Remove stale rows or sync the registry."
    )

    root = _click_root()
    problems = []

    for tool in sorted(PIPEFY_TOOL_NAMES):
        status, specs = rows[tool]
        if status in {"deferred", "n/a"}:
            continue
        if status == "pending":
            problems.append(
                f"{tool}: status is 'pending' (CLI not shipped). "
                "Ship the CLI command or mark deferred with rationale in Notes."
            )
            continue
        if status != "shipped":
            problems.append(f"{tool}: unexpected status {status!r} in docs/parity.md")
            continue
        if not specs:
            problems.append(
                f"{tool}: status shipped but no `pipefy ...` backtick command found in CLI column. "
                "Add at least one primary `pipefy …` invocation."
            )
            continue
        resolved = False
        for spec in specs:
            if not spec.startswith("pipefy"):
                continue
            tail = spec.removeprefix("pipefy").strip()
            tokens = _tokens_before_first_flag(tail)
            if tokens and _command_path_exists(root, tokens):
                resolved = True
                break
        if not resolved:
            joined = " ; ".join(specs)
            problems.append(
                f"{tool}: shipped in docs/parity.md but no listed CLI path exists on Typer app "
                f"(tried backtick specs: {joined}). Fix docs/parity.md or register the missing Typer command."
            )

    assert not problems, "Parity audit failed:\n" + "\n".join(problems)


@pytest.mark.parametrize("tool", sorted(PIPEFY_TOOL_NAMES))
def test_each_mcp_tool_has_documentation_row(tool):
    """Parametrized companion so ``pytest -k`` can target a single tool name."""
    rows = _parse_parity_rows(_PARITY_MD.read_text(encoding="utf-8"))
    assert tool in rows, f"{tool}: add a docs/parity.md matrix row"


def test_registry_tool_count_matches_documented_expectation():
    """Keep the parity doc header (``**128** tools``) honest; update docs when the registry changes."""
    text = _PARITY_MD.read_text(encoding="utf-8")
    m = re.search(r"\*\*(\d+)\*\*\s+tools", text)
    assert m is not None, (
        "docs/parity.md must document the expected MCP tool count near the top."
    )
    documented = int(m.group(1))
    assert len(PIPEFY_TOOL_NAMES) == documented, (
        f"PIPEFY_TOOL_NAMES has {len(PIPEFY_TOOL_NAMES)} tools but docs/parity.md documents {documented}. "
        "Update the **N** tools line and the matrix together."
    )
