"""The matching rule is implemented twice; this pins the two copies together.

``uninstall.sh`` decides whether a registration runs this toolkit in two
places: a python function for the JSON client configs, and a shell function
for the Codex TOML. The shell copy exists because the Codex path must work
without python3, which is also why it is the copy nobody exercises by hand —
a rule change applied to one and not the other diverges silently, in the
degraded path.

Neither implementation is read. Each case is written into a JSON client config
*and* into an equivalent Codex section, then one ``--scan`` observes both.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_uninstall_scan import _home, _run, _stub_path

# (label, entry fields, whether the rule must match it)
_CASES = [
    ("bare binary", {"command": "pipefy-mcp-server"}, True),
    ("absolute path", {"command": "/opt/tools/bin/pipefy-mcp-server"}, True),
    ("uvx runner", {"command": "uvx", "args": ["pipefy-mcp-server"]}, True),
    ("npx runner", {"command": "npx", "args": ["pipefy-mcp-server"]}, True),
    (
        "runner with a trailing flag",
        {"command": "uvx", "args": ["pipefy-mcp-server", "--profile", "core"]},
        True,
    ),
    ("hosted host", {"url": "https://mcp.pipefy.com/mcp"}, True),
    ("hosted host, upper case", {"url": "https://MCP.PIPEFY.COM/mcp"}, True),
    ("hosted host with a port", {"url": "https://mcp.pipefy.com:443/mcp"}, True),
    ("hosted host with a query", {"url": "https://mcp.pipefy.com/mcp?x=1"}, True),
    ("hosted host with userinfo", {"url": "https://u@mcp.pipefy.com/mcp"}, True),
    # Both fields at once. Which one a client honours varies, so either half
    # matching is enough and neither field can mask the other.
    (
        "both fields, ours in the command",
        {"command": "pipefy-mcp-server", "url": "https://other.example/mcp"},
        True,
    ),
    (
        "both fields, ours in the url",
        {"command": "some-proxy", "url": "https://mcp.pipefy.com/mcp"},
        True,
    ),
    # Must not match. Each is a near miss that a substring search would take.
    (
        "both fields, neither ours",
        {"command": "some-proxy", "url": "https://other.example/mcp"},
        False,
    ),
    (
        "runner whose argument merely starts with the binary",
        {"command": "uvx", "args": ["pipefy-mcp-server-extra"]},
        False,
    ),
    (
        "command that merely ends with the binary",
        {"command": "not-pipefy-mcp-server"},
        False,
    ),
    (
        "binary as an argument to a non-runner",
        {"command": "bash", "args": ["pipefy-mcp-server"]},
        False,
    ),
    (
        "hosted host as a prefix of another",
        {"url": "https://mcp.pipefy.com.other.example/mcp"},
        False,
    ),
    (
        "unrelated host containing the word",
        {"url": "https://builder.pipefy.example/mcp"},
        False,
    ),
    (
        "hosted host in the path, not the host",
        {"url": "https://other.example/mcp.pipefy.com"},
        False,
    ),
]

# A neutral key: `pipefy`-shaped names trip the separate "unverified" tier,
# which reports without claiming a match and would muddy the reading.
_NAME = "probe"


# Codex's TOML schema has no `type` key at all, so a case carrying one could
# not be rendered into both formats and is not a shared case. The JSON side of
# declared transports is covered in test_uninstall_scan.
def _toml_section(fields: dict) -> str:
    lines = [f"[mcp_servers.{_NAME}]"]
    if "command" in fields:
        lines.append(f'command = "{fields["command"]}"')
    if "url" in fields:
        lines.append(f'url = "{fields["url"]}"')
    if "args" in fields:
        rendered = ", ".join(f'"{a}"' for a in fields["args"])
        lines.append(f"args = [{rendered}]")
    return "\n".join(lines) + "\n"


def _plant(home: Path, fields: dict) -> None:
    (home / ".cursor").mkdir(parents=True, exist_ok=True)
    (home / ".cursor" / "mcp.json").write_text(
        json.dumps({"mcpServers": {_NAME: fields}}), encoding="utf-8"
    )
    (home / ".codex").mkdir(parents=True, exist_ok=True)
    (home / ".codex" / "config.toml").write_text(
        _toml_section(fields), encoding="utf-8"
    )


def _verdicts(out: str) -> tuple[bool, bool]:
    """(matched via the python JSON path, matched via the shell TOML path)."""
    return (
        f"client:cursor scope, named '{_NAME}'" in out,
        f"codex, section [mcp_servers.{_NAME}]" in out,
    )


@pytest.mark.parametrize(
    ("label", "fields", "expected"),
    _CASES,
    ids=[c[0].replace(" ", "-") for c in _CASES],
)
def test_both_copies_of_the_matching_rule_agree(tmp_path, label, fields, expected):
    home = _home(tmp_path)
    _plant(home, fields)
    out = _run(home, _stub_path(tmp_path)).stdout
    via_json, via_toml = _verdicts(out)

    assert via_json == via_toml, (
        f"{label}: the JSON matcher says {via_json} and the TOML matcher says "
        f"{via_toml}. The rule is implemented twice and the copies have drifted."
    )
    assert via_json is expected, f"{label}: expected match={expected}, got {via_json}"


@pytest.mark.parametrize(
    ("label", "fields", "expected"),
    _CASES,
    ids=[c[0].replace(" ", "-") for c in _CASES],
)
def test_the_toml_verdict_is_the_same_without_python3(
    tmp_path, label, fields, expected
):
    """The shell copy carries the Codex path alone when python3 is missing.

    That is the configuration the shell matcher exists for, so its verdict has
    to be identical to the one it gives when python3 is present.
    """
    home = _home(tmp_path)
    _plant(home, fields)
    out = _run(home, _stub_path(tmp_path, python3=False)).stdout
    _, via_toml = _verdicts(out)
    assert via_toml is expected, (
        f"{label}: without python3 the TOML matcher says {via_toml}, expected {expected}"
    )
