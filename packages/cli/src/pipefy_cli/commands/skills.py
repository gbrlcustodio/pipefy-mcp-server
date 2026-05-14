"""Skills subcommand — list and show bundled agent skill playbooks."""

from __future__ import annotations

import re
import sys
from importlib import resources
from pathlib import Path

import typer

skills_app = typer.Typer(
    help="Browse bundled agent skill playbooks.",
    no_args_is_help=True,
)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)
_FIELD_RE = re.compile(r"^(\w+)\s*:\s*(.+)$", re.MULTILINE)


def _bundled_skills_dir() -> Path:
    """Return the path to the bundled skills directory inside the installed package.

    Uses importlib.resources for installed wheels; falls back to the source layout
    when running from the repository with an editable install.
    """
    try:
        pkg_ref = resources.files("pipefy_cli") / "skills"
        resolved = Path(str(pkg_ref))
        if resolved.is_dir():
            return resolved
    except (TypeError, ModuleNotFoundError, FileNotFoundError):
        pass
    # Source layout fallback (editable installs, local dev)
    return Path(__file__).parent.parent / "skills"


def _parse_frontmatter(content: str) -> dict[str, str]:
    """Extract name and description from YAML frontmatter.

    Returns an empty dict when frontmatter is missing or malformed.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}
    fm_text = match.group(1)
    result: dict[str, str] = {}
    for field_match in _FIELD_RE.finditer(fm_text):
        key = field_match.group(1).strip()
        val = field_match.group(2).strip().strip(">").strip()
        result[key] = val
    return result


def _load_skills() -> list[tuple[str, str, str]]:
    """Load all bundled skills.

    Returns a list of (name, description, filepath) tuples sorted by name.
    """
    skills_dir = _bundled_skills_dir()
    if not skills_dir.is_dir():
        return []

    results: list[tuple[str, str, str]] = []
    for md_file in sorted(skills_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        fm = _parse_frontmatter(content)
        name = fm.get("name", md_file.stem)
        description = fm.get("description", "")
        # Collapse multiline description to a single line for display
        description = " ".join(description.split())
        results.append((name, description, str(md_file)))

    return results


@skills_app.command("list")
def skills_list() -> None:
    """List all bundled skills with their one-line descriptions."""
    skills = _load_skills()
    if not skills:
        typer.echo("No bundled skills found.", err=True)
        raise typer.Exit(1)

    for name, description, _ in skills:
        typer.echo(f"{name}")
        if description:
            typer.echo(f"  {description}")
        typer.echo()


@skills_app.command("show")
def skills_show(
    name: str = typer.Argument(..., help="Skill name (e.g. pipefy-pipes-and-cards)."),
) -> None:
    """Print the full content of a bundled skill to stdout.

    Args:
        name: Skill name matching the 'name' frontmatter field or the filename stem.
    """
    skills = _load_skills()
    if not skills:
        typer.echo("No bundled skills found.", err=True)
        raise typer.Exit(2)

    matched_path: str | None = None
    for skill_name, _, filepath in skills:
        if skill_name == name or Path(filepath).stem == name:
            matched_path = filepath
            break

    if matched_path is None:
        available = ", ".join(n for n, _, _ in skills)
        typer.echo(
            f"Skill '{name}' not found in bundled skills. Available: {available}",
            err=True,
        )
        raise typer.Exit(2)

    sys.stdout.write(Path(matched_path).read_text(encoding="utf-8"))
