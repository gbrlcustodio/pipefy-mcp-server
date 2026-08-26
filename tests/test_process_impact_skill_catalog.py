"""Catalog contracts for the process-impact skill and its routing hooks."""

from __future__ import annotations

import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SKILL_DIR = "skills/process-impact/pipefy-process-impact"
_SKILL_MD = _REPO / _SKILL_DIR / "SKILL.md"
_PLUGIN = _REPO / ".cursor-plugin" / "plugin.json"
_HOOKS = (
    _REPO / "skills" / "process-design" / "pipefy-process-design" / "SKILL.md",
    _REPO / "skills" / "process-intelligence" / "pipefy-process-intelligence" / "SKILL.md",
    _REPO / "skills" / "building" / "pipefy-building" / "SKILL.md",
    _REPO / "skills" / "README.md",
)

_HEADCOUNT_CUT_LANGUAGE = (
    "headcount",
    "layoff",
    "fte",
    "upsell",
)


def test_frontmatter_name_matches_directory():
    text = _SKILL_MD.read_text(encoding="utf-8")
    assert text.startswith("---"), _SKILL_MD
    assert "name: pipefy-process-impact" in text.split("---", 2)[1]


def test_plugin_manifest_lists_the_skill_directory():
    manifest = json.loads(_PLUGIN.read_text(encoding="utf-8"))
    assert f"./{_SKILL_DIR}" in manifest["skills"]


def test_design_intelligence_building_and_catalog_route_to_process_impact():
    for path in _HOOKS:
        text = path.read_text(encoding="utf-8")
        assert "pipefy-process-impact" in text, path


def test_public_skill_avoids_headcount_cut_language():
    lowered = _SKILL_MD.read_text(encoding="utf-8").casefold()
    for needle in _HEADCOUNT_CUT_LANGUAGE:
        assert needle not in lowered, needle
