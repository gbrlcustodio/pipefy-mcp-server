#!/usr/bin/env python3
"""Generate `pipefy_sdk.graphql_inputs` from the Pipefy GraphQL schema.

Three commands, and the split between them is what lets CI check the models
without credentials:

    snapshot   introspect the live API and rewrite packages/sdk/schema/input_types.json
    generate   rewrite _generated.py from that snapshot (the default)
    check      regenerate in memory and fail when it differs from the file on disk

`snapshot` is the only one that reaches the network, so it is run by hand after
an API change. `check` runs in CI and catches a hand-edit of the generated
module or a snapshot committed without regenerating. Catching the API itself
moving is the job of `test_input_types_snapshot_matches_live`, which is marked
`integration` and needs the credentials CI does not have.

Add a type to ROOT_INPUT_TYPES when its SDK method starts taking a typed input;
the transitive closure is resolved from there.
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import keyword
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = REPO_ROOT / "packages" / "sdk" / "schema" / "input_types.json"
PACKAGE_DIR = REPO_ROOT / "packages" / "sdk" / "src" / "pipefy_sdk" / "graphql_inputs"
GENERATED_PATH = PACKAGE_DIR / "_generated.py"
INIT_PATH = PACKAGE_DIR / "__init__.py"

PACKAGE_DOCSTRING = '''"""Typed inputs for the Pipefy GraphQL mutations the SDK writes to.

Each model mirrors one GraphQL input object: same field names, same
requiredness, same nesting. Constructing one rejects a misspelled or
unknown field by name, before any request is made.

`_generated.py` is written from a snapshot of the live schema by
`scripts/generate_graphql_inputs.py`. `_base.py` holds the parts that needed a
decision rather than a mapping. Neither this file nor `_generated.py` is
edited by hand.

`ConditionExpressionInput` here is the schema mirror. The separate
`pipefy_sdk.ConditionExpressionInput` is an older permissive model that the AI
automation surface still uses; the two converge when those methods take typed
inputs.
"""'''

# The input objects an SDK method takes directly. Everything they reference is
# pulled in transitively, so only the roots are listed. Grows one batch at a
# time as `**attrs` methods are migrated (#652).
ROOT_INPUT_TYPES: tuple[str, ...] = (
    "CreatePhaseFieldInput",
    "UpdateFieldConditionInput",
    "UpdateLabelInput",
    "UpdatePhaseFieldInput",
    "UpdatePhaseInput",
    "UpdatePipeInput",
    "createFieldConditionInput",
)

# Pipefy declares `createFieldCondition`'s input in camelCase where every other
# mutation uses PascalCase. The class keeps the Python convention and the
# snapshot keeps the wire name, so the mutation document is unaffected.
CLASS_NAME_OVERRIDES = {"createFieldConditionInput": "CreateFieldConditionInput"}

SCALAR_TYPES = {
    "Boolean": "bool",
    "Date": "str",
    "DateTime": "str",
    "DatetimeOrNumeric": "str",
    "Float": "float",
    "ID": "PipefyGraphQLId",
    "ISO8601Date": "str",
    "ISO8601DateTime": "str",
    "Int": "int",
    "JSON": "GraphQLJson",
    "Json": "GraphQLJson",
    "String": "str",
    "UndefinedInput": "GraphQLJson",
}

INTROSPECTION_QUERY = """
query {
  __schema {
    types {
      kind
      name
      description
      enumValues { name }
      inputFields {
        name
        description
        defaultValue
        type { kind name ofType { kind name ofType { kind name
          ofType { kind name ofType { kind name } } } } }
      }
    }
  }
}
"""


# --------------------------------------------------------------------------
# snapshot
# --------------------------------------------------------------------------


def _display_path(path: Path) -> str:
    """Repo-relative when it can be, absolute otherwise (a test may redirect it)."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _type_ref(node: dict[str, Any]) -> str:
    """Render an introspection type reference as GraphQL source, e.g. ``[ID!]!``."""
    if node["kind"] == "NON_NULL":
        return _type_ref(node["ofType"]) + "!"
    if node["kind"] == "LIST":
        return "[" + _type_ref(node["ofType"]) + "]"
    return node["name"]


def _named_type(type_ref: str) -> str:
    return type_ref.replace("[", "").replace("]", "").replace("!", "")


def build_snapshot(schema_types: list[dict[str, Any]]) -> dict[str, Any]:
    """Prune a full introspection result to the closure of ROOT_INPUT_TYPES."""
    by_name = {t["name"]: t for t in schema_types}
    inputs: dict[str, Any] = {}
    enums: dict[str, list[str]] = {}
    pending = list(ROOT_INPUT_TYPES)
    while pending:
        name = pending.pop()
        if name in inputs:
            continue
        node = by_name.get(name)
        if node is None or node["kind"] != "INPUT_OBJECT":
            raise SystemExit(f"{name} is not an INPUT_OBJECT in the live schema")
        fields = [
            {
                "name": f["name"],
                "type": _type_ref(f["type"]),
                "defaultValue": f["defaultValue"],
                "description": f["description"],
            }
            for f in node["inputFields"]
        ]
        inputs[name] = {"description": node["description"], "fields": fields}
        for field in fields:
            referenced = by_name.get(_named_type(field["type"]))
            if referenced is None:
                continue
            if referenced["kind"] == "INPUT_OBJECT":
                pending.append(referenced["name"])
            elif referenced["kind"] == "ENUM":
                enums[referenced["name"]] = [
                    v["name"] for v in referenced["enumValues"]
                ]
    return {
        "roots": sorted(ROOT_INPUT_TYPES),
        "enums": dict(sorted(enums.items())),
        "inputs": dict(sorted(inputs.items())),
    }


async def _introspect_live() -> list[dict[str, Any]]:
    from pipefy_auth import AuthSettings, build_httpx_auth, resolve_pipefy_auth
    from pipefy_sdk import PipefyClient
    from pipefy_sdk.settings import PipefySettings

    auth_settings = AuthSettings()
    resolved = resolve_pipefy_auth(
        service_account=auth_settings.to_service_account(),
        oidc_client=auth_settings.to_oidc_client(),
    )
    if resolved is None:
        raise SystemExit("No Pipefy credentials found. Run `pipefy auth login` first.")
    client = PipefyClient(
        PipefySettings(), auth=build_httpx_auth(resolved), surface="cli"
    )
    result = await client.execute_graphql(INTROSPECTION_QUERY)
    if "__schema" not in result:
        raise SystemExit(f"Introspection failed: {result}")
    return result["__schema"]["types"]


def command_snapshot() -> int:
    schema_types = asyncio.run(_introspect_live())
    snapshot = build_snapshot(schema_types)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2) + "\n")
    print(
        f"wrote {_display_path(SNAPSHOT_PATH)}: "
        f"{len(snapshot['inputs'])} input objects, {len(snapshot['enums'])} enums"
    )
    return 0


# --------------------------------------------------------------------------
# generate
# --------------------------------------------------------------------------


def class_name(graphql_name: str) -> str:
    return CLASS_NAME_OVERRIDES.get(graphql_name, graphql_name)


def enum_constant_name(graphql_name: str) -> str:
    """``PublicFormSubmitterEmailCollectionMethod`` -> ``..._VALUES``."""
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", graphql_name).upper()
    return f"{snake}_VALUES"


def python_type(type_ref: str, snapshot: dict[str, Any]) -> tuple[str, bool]:
    """Map a GraphQL type reference to a Python annotation and its requiredness.

    The annotation returned is the non-null form; the caller adds ``| None``.
    """
    if type_ref.endswith("!"):
        rendered, _ = python_type(type_ref[:-1], snapshot)
        return rendered, True
    if type_ref.startswith("["):
        item, item_required = python_type(type_ref[1:-1], snapshot)
        return f"list[{item if item_required else item + ' | None'}]", False
    if type_ref in snapshot["inputs"]:
        return class_name(type_ref), False
    if type_ref in snapshot["enums"]:
        # Soft enum, matching CONDITION_OPERATIONS: any string is sent and the
        # API validates it, so a value added server-side works without a release.
        return "str", False
    scalar = SCALAR_TYPES.get(type_ref)
    if scalar is None:
        raise SystemExit(f"No Python mapping for GraphQL scalar {type_ref!r}")
    return scalar, False


def field_attribute(graphql_name: str) -> tuple[str, str | None]:
    """Return the Python attribute name and the alias it needs, if any.

    Wire names are kept verbatim so a field reads the same in the model, the
    GraphQL document, and Pipefy's own docs — the schema mixes ``snake_case``
    and ``camelCase`` and neither spelling is the odd one out. Only a Python
    keyword forces a rename (``CreateAndSendInboxEmailInput.from``).
    """
    if keyword.iskeyword(graphql_name) or not graphql_name.isidentifier():
        return f"{graphql_name}_", graphql_name
    return graphql_name, None


def clean_description(raw: str | None) -> str:
    """Flatten a schema description onto one line.

    Pipefy writes the accepted values of several string-typed fields into the
    description as an indented bullet list (``CreatePhaseFieldInput.type`` names
    every field type that way). That list is the most useful part, so it is
    folded into the sentence rather than dropped.
    """
    if not raw:
        return ""
    bullets: list[str] = []
    prose: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
        else:
            prose.append(stripped)
    text = re.sub(r"\s+", " ", " ".join(prose)).strip()
    if re.fullmatch(r"Autogenerated input type of \w+", text):
        # Relay boilerplate that only restates the type name the docstring
        # already carries.
        return ""
    if bullets:
        separator = "" if text.endswith((".", ":")) else ":"
        text = f"{text}{separator} {', '.join(bullets)}.".strip()
    return text


def _ruff(arguments: list[str], source: str, path: Path) -> str:
    result = subprocess.run(
        ["ruff", *arguments, "--stdin-filename", str(path), "-"],
        input=source,
        capture_output=True,
        text=True,
        check=False,
    )
    if not result.stdout:
        raise SystemExit(
            f"ruff {' '.join(arguments)} produced nothing for "
            f"{path.name}:\n{result.stderr}"
        )
    return result.stdout


def _ruff_normalize(source: str, path: Path) -> str:
    """Sort imports, drop unused ones, then format, the way CI checks it.

    `ruff check` and `ruff format --check` run over the whole tree, so generated
    source that is not already clean fails the build. Deferring to ruff rather
    than replicating its import order keeps `check` honest — it compares against
    what a regeneration would actually write — and lets the renderer emit
    imports without knowing which of them each batch ends up using.
    """
    fixed = _ruff(["check", "--select", "I,F401", "--fix", "--quiet"], source, path)
    return _ruff(["format", "--quiet"], fixed, path)


def _topological_order(snapshot: dict[str, Any]) -> list[str]:
    """Order classes so a referenced model is always defined first."""
    ordered: list[str] = []
    placed: set[str] = set()

    def visit(name: str) -> None:
        if name in placed:
            return
        placed.add(name)
        for field in snapshot["inputs"][name]["fields"]:
            referenced = _named_type(field["type"])
            if referenced in snapshot["inputs"]:
                visit(referenced)
        ordered.append(name)

    for name in sorted(snapshot["inputs"], key=class_name):
        visit(name)
    return ordered


def _docstring(lines: list[str], indent: str) -> list[str]:
    body = [line for line in lines if line]
    if len(body) == 1:
        return [f'{indent}"""{body[0]}"""']
    out = [f'{indent}"""{body[0]}', indent.rstrip()]
    out.extend(f"{indent}{line}" if line else "" for line in body[1:])
    out.append(f'{indent}"""')
    return out


def render(snapshot: dict[str, Any]) -> tuple[str, list[str]]:
    """Render `_generated.py`, and return it with the names it exports."""
    out: list[str] = [
        "# @generated by scripts/generate_graphql_inputs.py — do not edit.",
        "#",
        "# Source: packages/sdk/schema/input_types.json, a pruned snapshot of the",
        "# Pipefy GraphQL schema. Regenerate with:",
        "#     uv run python scripts/generate_graphql_inputs.py",
        '"""Typed mirrors of the Pipefy GraphQL input objects the SDK writes to."""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Final",
        "",
        "from pydantic import Field",
        "",
        "from pipefy_sdk.graphql_inputs._base import (",
        "    GraphQLInput,",
        "    GraphQLJson,",
        "    PipefyGraphQLId,",
        ")",
        "",
    ]

    if snapshot["enums"]:
        out += [
            "# GraphQL enums are soft enums here: the field is typed `str` and any value",
            "# is sent, so a value added server-side works without an SDK release. These",
            "# tuples name the set the schema documents today.",
            "",
        ]
    for name, values in snapshot["enums"].items():
        out.append(f"{enum_constant_name(name)}: Final[tuple[str, ...]] = (")
        out += [f'    "{value}",' for value in values]
        out += [")", ""]

    exported: list[str] = [enum_constant_name(n) for n in snapshot["enums"]]
    for graphql_name in _topological_order(snapshot):
        spec = snapshot["inputs"][graphql_name]
        cls = class_name(graphql_name)
        exported.append(cls)
        out += ["", f"class {cls}(GraphQLInput):"]
        summary = f"Pipefy GraphQL ``{graphql_name}``."
        description = clean_description(spec["description"])
        out += _docstring(
            [summary, "", description] if description else [summary], "    "
        )
        out.append("")

        required = [f for f in spec["fields"] if f["type"].endswith("!")]
        optional = [f for f in spec["fields"] if not f["type"].endswith("!")]
        for field in required + optional:
            attribute, alias = field_attribute(field["name"])
            annotation, is_required = python_type(field["type"], snapshot)
            if not is_required:
                annotation += " | None"
            arguments: list[str] = []
            if not is_required:
                arguments.append("default=None")
            if alias is not None:
                arguments.append(f'alias="{alias}"')
            enum_name = _named_type(field["type"])
            note = (
                f"One of {enum_constant_name(enum_name)}; any value is sent."
                if enum_name in snapshot["enums"]
                else clean_description(field["description"])
            )
            if note:
                arguments.append(f"description={json.dumps(note)}")
            if arguments:
                out.append(
                    f"    {attribute}: {annotation} = Field({', '.join(arguments)})"
                )
            else:
                out.append(f"    {attribute}: {annotation}")
        out.append("")

    out += ["", "__all__ = ["]
    out += [f'    "{name}",' for name in sorted(exported)]
    out.append("]")
    return _ruff_normalize("\n".join(out) + "\n", GENERATED_PATH), sorted(exported)


BASE_EXPORTS = (
    "GraphQLInput",
    "GraphQLJson",
    "PipefyGraphQLId",
    "describe_input_rejection",
)


def render_init(generated_exports: list[str]) -> str:
    """Render the package `__init__`, so a new batch needs no hand edit here."""
    names = sorted([*BASE_EXPORTS, *generated_exports])
    out = [
        "# @generated by scripts/generate_graphql_inputs.py — do not edit.",
        PACKAGE_DOCSTRING,
        "",
        "from __future__ import annotations",
        "",
        "from pipefy_sdk.graphql_inputs._base import (",
        *[f"    {name}," for name in BASE_EXPORTS],
        ")",
        "from pipefy_sdk.graphql_inputs._generated import (",
        *[f"    {name}," for name in generated_exports],
        ")",
        "",
        "__all__ = [",
        *[f'    "{name}",' for name in names],
        "]",
    ]
    return _ruff_normalize("\n".join(out) + "\n", INIT_PATH)


def render_all(snapshot: dict[str, Any]) -> dict[Path, str]:
    generated, exports = render(snapshot)
    return {GENERATED_PATH: generated, INIT_PATH: render_init(exports)}


def load_snapshot() -> dict[str, Any]:
    if not SNAPSHOT_PATH.exists():
        raise SystemExit(
            f"{_display_path(SNAPSHOT_PATH)} is missing. "
            "Run `generate_graphql_inputs.py snapshot` with Pipefy credentials."
        )
    return json.loads(SNAPSHOT_PATH.read_text())


def command_generate() -> int:
    for path, source in render_all(load_snapshot()).items():
        path.write_text(source)
        print(f"wrote {_display_path(path)}")
    return 0


def command_check() -> int:
    stale = False
    for path, expected in render_all(load_snapshot()).items():
        actual = path.read_text() if path.exists() else ""
        if expected == actual:
            continue
        stale = True
        sys.stdout.writelines(
            difflib.unified_diff(
                actual.splitlines(keepends=True),
                expected.splitlines(keepends=True),
                fromfile=f"{_display_path(path)} (on disk)",
                tofile=f"{_display_path(path)} (regenerated)",
            )
        )
    if stale:
        print(
            "\nThe generated models do not match the snapshot. Run:\n"
            "    uv run python scripts/generate_graphql_inputs.py",
            file=sys.stderr,
        )
        return 1
    print("pipefy_sdk.graphql_inputs is up to date")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "command",
        nargs="?",
        default="generate",
        choices=("snapshot", "generate", "check"),
    )
    command = parser.parse_args(argv).command
    return {
        "snapshot": command_snapshot,
        "generate": command_generate,
        "check": command_check,
    }[command]()


if __name__ == "__main__":
    raise SystemExit(main())
