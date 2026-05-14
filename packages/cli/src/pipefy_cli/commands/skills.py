"""Skills subcommand — list and show bundled agent skill playbooks."""

from __future__ import annotations

import re
import sys
from importlib import resources
from pathlib import Path
from typing import TypedDict

import typer
import yaml

skills_app = typer.Typer(
    help="Browse bundled agent skill playbooks.",
    no_args_is_help=True,
)

_FRONTMATTER_RE = re.compile(
    r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n",
    re.DOTALL,
)


class BundledSkillMeta(TypedDict):
    """One bundled skill entry for list/show."""

    name: str
    description: str
    path: str


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
    """Extract YAML frontmatter keys as single-line string values.

    Args:
        content: Full Markdown file contents.

    Returns:
        Mapping of frontmatter keys to normalized string values, or empty dict
        when frontmatter is missing.

    Raises:
        yaml.YAMLError: When the frontmatter block is present but not valid YAML.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}
    data = yaml.safe_load(match.group(1))
    if data is None:
        return {}
    if not isinstance(data, dict):
        msg = "frontmatter root must be a mapping"
        raise yaml.YAMLError(msg)
    out: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            continue
        if value is None:
            out[key] = ""
        elif isinstance(value, str):
            out[key] = " ".join(value.split())
        else:
            out[key] = " ".join(str(value).split())
    return out


def _load_skills() -> tuple[list[BundledSkillMeta], list[str]]:
    """Load all bundled skills.

    Returns:
        Tuple of (skills sorted by name, YAML parse error messages with paths).
    """
    skills_dir = _bundled_skills_dir()
    if not skills_dir.is_dir():
        return [], []

    results: list[BundledSkillMeta] = []
    errors: list[str] = []
    for md_file in sorted(skills_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        try:
            fm = _parse_frontmatter(content)
        except yaml.YAMLError as exc:
            errors.append(f"{md_file}: invalid YAML frontmatter ({exc})")
            continue
        name = fm.get("name", md_file.stem)
        description = fm.get("description", "")
        results.append(
            BundledSkillMeta(name=name, description=description, path=str(md_file))
        )

    results.sort(key=lambda s: s["name"])
    return results, errors


def _skill_matches_query(skill: BundledSkillMeta, query: str) -> bool:
    """Return True if ``query`` selects this bundled skill.

    Args:
        skill: Loaded bundled skill metadata.
        query: User argument (``name`` field, filename stem, or unprefixed slug).
    """
    stem = Path(skill["path"]).stem
    skill_name = skill["name"]
    if skill_name == query or stem == query:
        return True
    if skill_name == f"pipefy-{query}":
        return True
    if stem == f"pipefy-{query}":
        return True
    return False


@skills_app.command("list")
def skills_list() -> None:
    """List all bundled skills with their one-line descriptions."""
    skills, yaml_errors = _load_skills()
    if yaml_errors:
        for line in yaml_errors:
            typer.echo(line, err=True)
        raise typer.Exit(2)
    if not skills:
        typer.echo("No bundled skills found.", err=True)
        raise typer.Exit(2)

    for skill in skills:
        typer.echo(skill["name"])
        if skill["description"]:
            typer.echo(f"  {skill['description']}")
        typer.echo()


@skills_app.command("show")
def skills_show(
    name: str = typer.Argument(..., help="Skill name (e.g. pipefy-pipes-and-cards)."),
) -> None:
    """Print the full content of a bundled skill to stdout.

    Args:
        name: Skill name matching the 'name' frontmatter field, the filename stem,
            or the slug without the ``pipefy-`` prefix (e.g. ``pipes-and-cards``).
    """
    skills, yaml_errors = _load_skills()
    if yaml_errors:
        for line in yaml_errors:
            typer.echo(line, err=True)
        raise typer.Exit(2)
    if not skills:
        typer.echo("No bundled skills found.", err=True)
        raise typer.Exit(2)

    matched_path: str | None = None
    for skill in skills:
        if _skill_matches_query(skill, name):
            matched_path = skill["path"]
            break

    if matched_path is None:
        available = ", ".join(s["name"] for s in skills)
        typer.echo(
            f"Skill '{name}' not found in bundled skills. Available: {available}",
            err=True,
        )
        raise typer.Exit(2)

    sys.stdout.write(Path(matched_path).read_text(encoding="utf-8"))
