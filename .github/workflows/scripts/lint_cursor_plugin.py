#!/usr/bin/env python3
"""Validate Cursor plugin packaging: manifest, published skill set, and mcp.json."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_TEMPLATE_PREFIX = "skills/_template/"

PLUGIN_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$")
PLACEHOLDER_RE = re.compile(r"\$\{[^}]*\}")
PATH_LIST_FIELDS = ("skills", "commands", "agents", "rules", "hooks")
ALLOWED_MCP_TOP_LEVEL_KEYS = ("mcpServers",)
ALLOWED_MCP_SERVER_KEYS = ("url", "auth")
ALLOWED_MCP_AUTH_KEYS = ("CLIENT_ID",)
FORBIDDEN_MANIFEST_KEYS = ("mcpServers", "variables")
HOSTED_SERVER_NAME = "pipefy"
HOSTED_MCP_URL = "https://mcp.pipefy.com/mcp"
HOSTED_CLIENT_ID = "pipefy-mcp"


def _rel(root: Path, path: Path) -> Path:
    return path.relative_to(root)


def _load_json(root: Path, path: Path) -> dict[str, Any] | str:
    rel = _rel(root, path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"could not read {rel}: {exc}"
    except UnicodeDecodeError as exc:
        return f"{rel} is not valid UTF-8: {exc}; expected UTF-8 text"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return f"{rel} is not valid JSON: {exc}; expected a JSON object"
    if not isinstance(data, dict):
        return f"{rel} parsed as {type(data).__name__}, expected a JSON object"
    return data


def _normalize_repo_rel(raw: str) -> str:
    return raw.replace("\\", "/").removeprefix("./").rstrip("/")


def skill_dirs_from_ls_files(lines: list[str]) -> set[str]:
    """Published skill directories: parents of tracked SKILL.md, minus the template."""
    dirs: set[str] = set()
    for line in lines:
        posix = line.replace("\\", "/")
        if posix.startswith(SKILL_TEMPLATE_PREFIX):
            continue
        dirs.add(_normalize_repo_rel(Path(posix).parent.as_posix()))
    return dirs


def _tracked_skill_md_paths(root: Path) -> list[str] | str:
    proc = subprocess.run(
        ["git", "ls-files", "--", "skills/**/SKILL.md"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "no output"
        return (
            f"git ls-files failed with exit {proc.returncode} "
            f"(cwd={root}, pathspec='skills/**/SKILL.md'): {detail}"
        )
    return proc.stdout.splitlines()


def _path_field_error(
    root: Path, manifest_rel: Path, field: str, raw: str
) -> str | None:
    if not raw.strip():
        return (
            f"{manifest_rel} field {field} has empty path {raw!r}, "
            "expected a relative path with no '..'"
        )
    if Path(raw).is_absolute():
        return (
            f"{manifest_rel} field {field} has absolute path {raw!r}, "
            "expected a relative path with no '..'"
        )
    parts = Path(_normalize_repo_rel(raw)).parts
    if ".." in parts:
        return (
            f"{manifest_rel} field {field} has path {raw!r} containing '..', "
            "expected a relative path inside the repository"
        )
    target = root / raw
    if not target.exists():
        return (
            f"{manifest_rel} field {field} path {raw!r} does not exist on disk, "
            f"expected a relative path that exists under {root}"
        )
    if field == "logo" and target.is_dir():
        return (
            f"{manifest_rel} field {field} path {raw!r} is a directory, expected a file"
        )
    return None


def _iter_path_values(manifest: dict[str, Any]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for field in PATH_LIST_FIELDS:
        value = manifest.get(field)
        if isinstance(value, list):
            found.extend((field, item) for item in value if isinstance(item, str))
        elif isinstance(value, str):
            found.append((field, value))
    return found


def _lint_plugin_name(manifest_rel: Path, manifest: dict[str, Any]) -> list[str]:
    name = manifest.get("name")
    if not isinstance(name, str) or PLUGIN_NAME_RE.fullmatch(name) is None:
        return [
            f"{manifest_rel} name is {name!r}, expected a string matching "
            "^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$"
        ]
    return []


def _lint_forbidden_manifest_keys(
    manifest_rel: Path, manifest: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    for key in FORBIDDEN_MANIFEST_KEYS:
        if key in manifest:
            errors.append(
                f"{manifest_rel} declares {key}, which this plugin must not "
                f"ship; expected no {key} field"
            )
    return errors


def _lint_commands_suppressed(
    manifest_rel: Path, manifest: dict[str, Any]
) -> list[str]:
    commands = manifest.get("commands")
    if commands != []:
        return [
            f"{manifest_rel} commands is {commands!r}, expected an empty list "
            "so Cursor does not discover the repo-root commands/ directory"
        ]
    return []


def _lint_logo(root: Path, manifest_rel: Path, manifest: dict[str, Any]) -> list[str]:
    if "logo" not in manifest:
        return [
            f"{manifest_rel} logo is missing, expected a relative file path or "
            "https URL"
        ]
    logo = manifest["logo"]
    if not isinstance(logo, str) or not logo.strip():
        return [
            f"{manifest_rel} logo is {logo!r}, expected a non-empty relative "
            "file path or https URL"
        ]
    if logo.startswith("https://"):
        return []
    err = _path_field_error(root, manifest_rel, "logo", logo)
    return [err] if err is not None else []


def _lint_skill_set(
    manifest_rel: Path, manifest: dict[str, Any], tree: set[str]
) -> list[str]:
    skills = manifest.get("skills")
    if not isinstance(skills, list) or not all(
        isinstance(item, str) for item in skills
    ):
        return [
            f"{manifest_rel} skills is {skills!r}, expected a list of relative "
            "skill directories"
        ]
    declared = {_normalize_repo_rel(item) for item in skills}
    errors: list[str] = []
    for path in sorted(tree - declared):
        errors.append(
            f"skills array is missing {path!r}; expected the manifest to list "
            "every published skill directory from git ls-files "
            "'skills/**/SKILL.md' excluding skills/_template/"
        )
    for path in sorted(declared - tree):
        errors.append(
            f"skills array lists {path!r}, which is not a tracked skill "
            "directory; expected a path from git ls-files "
            "'skills/**/SKILL.md' excluding skills/_template/"
        )
    return errors


def _lint_hosted_auth(rel: Path, name: str, server: dict[str, Any]) -> list[str]:
    """Check ``auth`` against the allowlist ADR-004 pins.

    Unexpected keys are named but never echoed: an unenumerated key is exactly
    where a committed credential would sit, and this message reaches public CI
    logs.
    """
    errors: list[str] = []
    auth = server.get("auth")
    if not isinstance(auth, dict):
        errors.append(
            f"{rel} server {name!r} has auth={auth!r}, expected an object "
            f"with CLIENT_ID {HOSTED_CLIENT_ID!r}"
        )
        return errors
    client_id = auth.get("CLIENT_ID")
    if client_id != HOSTED_CLIENT_ID:
        errors.append(
            f"{rel} server {name!r} has auth.CLIENT_ID={client_id!r}, "
            f"expected {HOSTED_CLIENT_ID!r}"
        )
    for key in sorted(set(auth) - set(ALLOWED_MCP_AUTH_KEYS)):
        errors.append(
            f"{rel} server {name!r} has unexpected auth key {key!r}; expected "
            f"only {', '.join(ALLOWED_MCP_AUTH_KEYS)} on a URL-only server"
        )
    return errors


def _lint_mcp(root: Path, mcp_path: Path) -> list[str]:
    loaded = _load_json(root, mcp_path)
    if isinstance(loaded, str):
        return [loaded]
    servers = loaded.get("mcpServers")
    rel = _rel(root, mcp_path)
    if not isinstance(servers, dict):
        return [
            f"{rel} mcpServers is {servers!r}, expected an object with exactly "
            "one server"
        ]
    if len(servers) != 1:
        return [
            f"{rel} declares {len(servers)} server(s) {list(servers)!r}, "
            "expected exactly one"
        ]
    errors: list[str] = []
    for key in sorted(set(loaded) - set(ALLOWED_MCP_TOP_LEVEL_KEYS)):
        errors.append(
            f"{rel} has unexpected top-level key {key!r}; expected only "
            f"{', '.join(ALLOWED_MCP_TOP_LEVEL_KEYS)}"
        )
    name, server = next(iter(servers.items()))
    if not isinstance(server, dict):
        return [
            f"{rel} server {name!r} is {server!r}, expected an object with a "
            "url and no command, args, or env"
        ]
    if name != HOSTED_SERVER_NAME:
        errors.append(f"{rel} server key is {name!r}, expected {HOSTED_SERVER_NAME!r}")
    url = server.get("url")
    if url != HOSTED_MCP_URL:
        errors.append(
            f"{rel} server {name!r} has url={url!r}, expected {HOSTED_MCP_URL!r}"
        )
    for key in sorted(set(server) - set(ALLOWED_MCP_SERVER_KEYS)):
        errors.append(
            f"{rel} server {name!r} has unexpected key {key!r}; expected only "
            f"{', '.join(ALLOWED_MCP_SERVER_KEYS)} on a URL-only server"
        )
    errors.extend(_lint_hosted_auth(rel, name, server))
    try:
        text = mcp_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"could not re-read {rel} for placeholder scan: {exc}")
        return errors
    match = PLACEHOLDER_RE.search(text)
    if match is not None:
        errors.append(
            f"{rel} contains placeholder {match.group(0)!r}; expected no "
            "${...} placeholders"
        )
    return errors


def collect_errors(root: Path, skill_md_paths: list[str]) -> list[str]:
    """Return packaging errors for a plugin rooted at ``root``.

    ``skill_md_paths`` is the ``git ls-files 'skills/**/SKILL.md'`` listing
    (template rows included; they are dropped here).
    """
    manifest_path = root / ".cursor-plugin/plugin.json"
    mcp_path = root / "mcp.json"
    loaded = _load_json(root, manifest_path)
    if isinstance(loaded, str):
        return [loaded]

    manifest_rel = _rel(root, manifest_path)
    errors: list[str] = []
    errors.extend(_lint_plugin_name(manifest_rel, loaded))
    errors.extend(_lint_forbidden_manifest_keys(manifest_rel, loaded))
    errors.extend(_lint_commands_suppressed(manifest_rel, loaded))
    errors.extend(_lint_logo(root, manifest_rel, loaded))
    errors.extend(
        _lint_skill_set(manifest_rel, loaded, skill_dirs_from_ls_files(skill_md_paths))
    )
    for field, raw in _iter_path_values(loaded):
        err = _path_field_error(root, manifest_rel, field, raw)
        if err is not None:
            errors.append(err)
    errors.extend(_lint_mcp(root, mcp_path))
    return errors


def main() -> int:
    listing = _tracked_skill_md_paths(REPO_ROOT)
    if isinstance(listing, str):
        print("Cursor plugin packaging FAILED:", file=sys.stderr)
        print(f"  {listing}", file=sys.stderr)
        return 1

    errors = collect_errors(REPO_ROOT, listing)
    if errors:
        print("Cursor plugin packaging FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("Cursor plugin packaging passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
