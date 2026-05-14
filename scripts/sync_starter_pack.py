#!/usr/bin/env python3
"""Copy canonical starter-pack skills into the CLI wheel bundle."""

from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Canonical SKILL.md -> bundled filename (must match hatch wheel includes).
STARTER_PACK: tuple[tuple[Path, Path], ...] = (
    (
        REPO_ROOT / "skills/pipes-and-cards/pipefy-pipes-and-cards/SKILL.md",
        REPO_ROOT / "packages/cli/src/pipefy_cli/skills/pipefy-pipes-and-cards.md",
    ),
    (
        REPO_ROOT / "skills/process-design/pipefy-process-design/SKILL.md",
        REPO_ROOT / "packages/cli/src/pipefy_cli/skills/pipefy-process-design.md",
    ),
    (
        REPO_ROOT / "skills/relations/pipefy-relations/SKILL.md",
        REPO_ROOT / "packages/cli/src/pipefy_cli/skills/pipefy-relations.md",
    ),
    (
        REPO_ROOT / "skills/database-tables/pipefy-database-tables/SKILL.md",
        REPO_ROOT / "packages/cli/src/pipefy_cli/skills/pipefy-database-tables.md",
    ),
    (
        REPO_ROOT / "skills/introspection/pipefy-introspection/SKILL.md",
        REPO_ROOT / "packages/cli/src/pipefy_cli/skills/pipefy-introspection.md",
    ),
    (
        REPO_ROOT / "skills/automations/pipefy-automations/SKILL.md",
        REPO_ROOT / "packages/cli/src/pipefy_cli/skills/pipefy-automations.md",
    ),
    (
        REPO_ROOT / "skills/ai-agents/pipefy-ai-agents/SKILL.md",
        REPO_ROOT / "packages/cli/src/pipefy_cli/skills/pipefy-ai-agents.md",
    ),
    (
        REPO_ROOT / "skills/observability/pipefy-observability/SKILL.md",
        REPO_ROOT / "packages/cli/src/pipefy_cli/skills/pipefy-observability.md",
    ),
)


def verify_bundle_matches_canonical() -> list[str]:
    """Return human-readable drift messages when any bundled file differs from canonical.

    Returns:
        Empty list when every pair matches; otherwise one message per mismatch.
    """
    drift: list[str] = []
    for src, dst in STARTER_PACK:
        if not src.is_file():
            drift.append(f"missing canonical: {src.relative_to(REPO_ROOT)}")
            continue
        if not dst.is_file():
            drift.append(f"missing bundled: {dst.relative_to(REPO_ROOT)}")
            continue
        if not filecmp.cmp(src, dst, shallow=False):
            drift.append(
                f"content differs: {dst.relative_to(REPO_ROOT)} "
                f"!= {src.relative_to(REPO_ROOT)}",
            )
    return drift


def main() -> int:
    """Copy each canonical skill into the CLI package, or verify there is no drift.

    Returns:
        0 on success, 1 if a canonical file is missing or ``--check`` finds drift.
    """
    check_only = "--check" in sys.argv[1:]

    missing: list[Path] = []
    for src, _dst in STARTER_PACK:
        if not src.is_file():
            missing.append(src)
    if missing:
        for path in missing:
            print(f"Missing canonical skill: {path}", file=sys.stderr)
        return 1

    if check_only:
        drift = verify_bundle_matches_canonical()
        if drift:
            print("Starter pack bundle drift detected:", file=sys.stderr)
            for line in drift:
                print(f"  {line}", file=sys.stderr)
            return 1
        print("Starter pack bundle matches canonical skills.")
        return 0

    for src, dst in STARTER_PACK:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"Synced {src.relative_to(REPO_ROOT)} -> {dst.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
