"""Rewrap FastMCP argument-validation errors as canonical tool-error envelopes.

FastMCP's ``Tool.run`` catches any exception raised by
``fn_metadata.call_fn_with_arg_validation`` and wraps it as
``ToolError(f"Error executing tool {name}: {e}")``. For argument coercion
failures the underlying cause is a ``pydantic.ValidationError`` whose default
string rendering leaks implementation details (``pydantic.dev`` URLs, internal
``Arguments`` class names). :class:`PipefyValidationTool` intercepts that
``ToolError`` *before* it reaches the MCP transport layer and returns a
``{"success": False, "error": {...}}`` payload with an agent-friendly message.

Install once at server startup via :func:`install_pipefy_validation_envelope`.
The patch is idempotent so repeated startup (e.g. in tests) does not stack.

Tested against ``mcp == 1.25.0`` (``Tool.run`` signature in
``mcp.server.fastmcp.tools.base``). If the upstream package is upgraded,
re-verify the ``call_fn_with_arg_validation`` / ``Tool.run`` contract.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.tools.base import Tool
from mcp.server.fastmcp.tools.tool_manager import ToolManager
from pydantic import ValidationError

from pipefy_mcp.tools.tool_error_envelope import tool_error

if TYPE_CHECKING:
    from collections.abc import Callable

    from mcp.server.fastmcp.server import Context
    from mcp.server.session import ServerSessionT
    from mcp.shared.context import LifespanContextT, RequestT
    from mcp.types import Icon, ToolAnnotations

__all__ = [
    "INVALID_ARGUMENTS_CODE",
    "PipefyValidationTool",
    "install_pipefy_validation_envelope",
]

logger = logging.getLogger(__name__)

INVALID_ARGUMENTS_CODE = "INVALID_ARGUMENTS"
_PATCH_SENTINEL = "_pipefy_validation_envelope_patched"


def _format_validation_errors(exc: ValidationError, tool_name: str) -> str:
    """Render a ``ValidationError`` as a single agent-friendly line.

    The output never contains ``pydantic.dev`` URLs nor FastMCP-internal
    ``Arguments`` model names. Each error becomes a short clause; clauses are
    joined with ``"; "`` and prefixed with the offending tool name.
    """
    clauses: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", ()))
        err_type = err.get("type", "")
        msg = err.get("msg", "")
        if err_type == "missing":
            clauses.append(f"missing required argument '{loc}'")
        elif err_type == "extra_forbidden":
            clauses.append(f"unknown argument '{loc}'")
        elif loc:
            clauses.append(f"{loc}: {msg}")
        else:
            clauses.append(msg)
    joined = "; ".join(clause for clause in clauses if clause)
    return f"Tool '{tool_name}' received invalid arguments: {joined}"


def _serialize_errors(exc: ValidationError) -> list[dict[str, Any]]:
    """Return a minimal JSON-serializable list for ``details.errors``.

    Only keeps ``path``, ``type``, and ``message`` so the response stays free
    of Pydantic URLs and input echoes (which may contain secrets).
    """
    serialized: list[dict[str, Any]] = []
    for err in exc.errors():
        serialized.append(
            {
                "path": list(err.get("loc", ())),
                "type": err.get("type", ""),
                "message": err.get("msg", ""),
            }
        )
    return serialized


class PipefyValidationTool(Tool):
    """FastMCP ``Tool`` subclass that intercepts argument-validation errors.

    ``Tool.run`` wraps any exception as a ``ToolError`` whose ``__cause__`` is
    the underlying exception. We re-inspect that chain: when the cause is a
    ``ValidationError`` from the tool's own arg-model (not an inner body
    validation), we swap the ``ToolError`` for a canonical
    ``{"success": False, "error": {...}}`` payload.
    """

    async def run(
        self,
        arguments: dict[str, Any],
        context: Context[ServerSessionT, LifespanContextT, RequestT] | None = None,
        convert_result: bool = False,
    ) -> Any:
        """Run the tool, rewrapping arg-coercion ``ValidationError`` as an envelope."""
        try:
            return await super().run(
                arguments, context=context, convert_result=convert_result
            )
        except ToolError as exc:
            cause = exc.__cause__
            if isinstance(cause, ValidationError) and self._is_arg_model_error(cause):
                payload = tool_error(
                    _format_validation_errors(cause, self.name),
                    code=INVALID_ARGUMENTS_CODE,
                    details={"errors": _serialize_errors(cause)},
                )
                if convert_result:
                    payload = self.fn_metadata.convert_result(payload)
                return payload
            raise

    def _is_arg_model_error(self, exc: ValidationError) -> bool:
        """True when the ``ValidationError`` was raised by our arg-coercion step.

        Pydantic v2 sets ``ValidationError.title`` to the model class name.
        ``FuncMetadata`` constructs a per-tool arg model named ``<fn>Arguments``;
        matching on that name keeps inner-body ``ValidationError`` cases (e.g. a
        tool manually calling ``SomeModel.model_validate(...)``) untouched.
        """
        return exc.title == self.fn_metadata.arg_model.__name__


def install_pipefy_validation_envelope() -> None:
    """Monkey-patch ``ToolManager.add_tool`` so every registered tool uses the envelope.

    Idempotent: re-invocation is a no-op, which keeps repeated server startup
    (in tests) from stacking patches.
    """
    if getattr(ToolManager, _PATCH_SENTINEL, False):
        return

    def _add_tool(
        self: ToolManager,
        fn: Callable[..., Any],
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        annotations: ToolAnnotations | None = None,
        icons: list[Icon] | None = None,
        meta: dict[str, Any] | None = None,
        structured_output: bool | None = None,
    ) -> Tool:
        tool = PipefyValidationTool.from_function(
            fn,
            name=name,
            title=title,
            description=description,
            annotations=annotations,
            icons=icons,
            meta=meta,
            structured_output=structured_output,
        )
        existing = self._tools.get(tool.name)
        if existing:
            if self.warn_on_duplicate_tools:
                logger.warning("Tool already exists: %s", tool.name)
            return existing
        self._tools[tool.name] = tool
        return tool

    ToolManager.add_tool = _add_tool  # type: ignore[assignment]
    setattr(ToolManager, _PATCH_SENTINEL, True)
    logger.debug("PipefyValidationTool wiring active (ToolManager.add_tool patched)")
