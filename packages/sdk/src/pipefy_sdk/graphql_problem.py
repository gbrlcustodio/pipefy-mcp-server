"""Standalone GraphQL error classifier shared across the SDK, CLI, and MCP.

Maps a Pipefy GraphQL error payload (or the ``TransportQueryError`` that
carries it) onto a small closed set of structured problems: permission denied,
not found, invalid arguments, feature not enabled, or an unclassified runtime
error. Provider probes and CLI write-gating consume this instead of each
re-deriving ``except``-mapping locally.

It lives in the SDK on purpose. The richer MCP enrichment
(``pipefy_mcp.tools.graphql_error_helpers``) imports MCP settings and the MCP
response envelope, so neither the SDK nor the CLI can import it. This module
depends on nothing beyond the standard library and the ``gql`` error shape the
SDK already surfaces, so all three layers can share one classifier.

Classification reads ``extensions.code`` first (the authoritative signal the
Pipefy GraphQL layer attaches) and falls back to substring markers on the
message only for not-found, where legacy paths omit a code. An error the
classifier does not recognize maps to :attr:`GraphQLProblemKind.RUNTIME` rather
than being forced into a more specific bucket.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = [
    "GraphQLProblem",
    "GraphQLProblemKind",
    "classify_graphql_error_dicts",
    "classify_exception",
]


class GraphQLProblemKind(str, Enum):
    """The closed set of structured problems the classifier resolves.

    ``FEATURE_NOT_ENABLED`` is reserved for the (rare) explicit feature-flag
    error codes; the provider read surface signals a disabled feature by an
    empty system-provider list rather than an error, so probes infer that case
    separately from this classification.
    """

    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    INVALID_ARGUMENTS = "invalid_arguments"
    FEATURE_NOT_ENABLED = "feature_not_enabled"
    RUNTIME = "runtime"


# extensions.code values the Pipefy GraphQL API attaches, grouped by the
# problem they map to (PERMISSION_DENIED, RESOURCE_NOT_FOUND / RECORD_NOT_FOUND,
# RECORD_INVALID, ...). The extra synonyms guard against endpoints that use the
# more generic GraphQL spellings.
_PERMISSION_CODES = frozenset({"PERMISSION_DENIED", "FORBIDDEN", "UNAUTHORIZED"})
_NOT_FOUND_CODES = frozenset({"NOT_FOUND", "RESOURCE_NOT_FOUND", "RECORD_NOT_FOUND"})
_INVALID_ARGUMENT_CODES = frozenset(
    {"INVALID_ARGUMENTS", "BAD_USER_INPUT", "RECORD_INVALID", "ARGUMENT_ERROR"}
)
_FEATURE_CODES = frozenset(
    {"FEATURE_NOT_ENABLED", "FEATURE_DISABLED", "FEATURE_UNAVAILABLE"}
)

_NOT_FOUND_MESSAGE_MARKERS = (
    "not found",
    "does not exist",
    "doesn't exist",
    "couldn't find",
)

_CODE_TO_KIND: dict[str, GraphQLProblemKind] = {
    **{c: GraphQLProblemKind.PERMISSION_DENIED for c in _PERMISSION_CODES},
    **{c: GraphQLProblemKind.NOT_FOUND for c in _NOT_FOUND_CODES},
    **{c: GraphQLProblemKind.INVALID_ARGUMENTS for c in _INVALID_ARGUMENT_CODES},
    **{c: GraphQLProblemKind.FEATURE_NOT_ENABLED for c in _FEATURE_CODES},
}


@dataclass(frozen=True)
class GraphQLProblem:
    """A classified GraphQL error: what kind it is, plus the raw diagnostics.

    ``code`` and ``correlation_id`` are carried verbatim from ``extensions`` so
    callers can surface them for support without re-parsing the error.
    """

    kind: GraphQLProblemKind
    message: str
    code: str | None = None
    correlation_id: str | None = None


def _kind_from_code(code: str | None) -> GraphQLProblemKind | None:
    if not code:
        return None
    return _CODE_TO_KIND.get(code.strip().upper())


def _kind_from_message(message: str) -> GraphQLProblemKind | None:
    lowered = message.lower()
    if any(marker in lowered for marker in _NOT_FOUND_MESSAGE_MARKERS):
        return GraphQLProblemKind.NOT_FOUND
    return None


def classify_graphql_error_dicts(
    errors: list[dict[str, Any]],
) -> GraphQLProblem | None:
    """Classify the first error in a GraphQL ``errors`` list.

    Returns ``None`` for an empty list. A recognized ``extensions.code`` wins;
    otherwise a not-found substring marker on the message is honored; anything
    else classifies as :attr:`GraphQLProblemKind.RUNTIME` (still a problem, just
    unclassified) so callers always get a structured result for a real error.
    """
    if not errors:
        return None
    first = errors[0] if isinstance(errors[0], dict) else {}
    extensions = (
        first.get("extensions") if isinstance(first.get("extensions"), dict) else {}
    )
    code_raw = extensions.get("code")
    code = str(code_raw) if code_raw not in (None, "") else None
    correlation_raw = extensions.get("correlation_id")
    correlation_id = str(correlation_raw) if correlation_raw not in (None, "") else None
    message = str(first.get("message") or "Unknown error")

    kind = (
        _kind_from_code(code)
        or _kind_from_message(message)
        or GraphQLProblemKind.RUNTIME
    )
    return GraphQLProblem(
        kind=kind,
        message=message,
        code=code,
        correlation_id=correlation_id,
    )


def classify_exception(exc: BaseException) -> GraphQLProblem | None:
    """Classify an exception raised by the GraphQL executor.

    Handles the public endpoint's ``TransportQueryError`` (and any exception
    that duck-types it) by reading its ``errors`` list. Returns ``None`` when
    the exception carries no GraphQL error dicts, so callers can distinguish a
    classified GraphQL problem from a transport/network failure they should
    re-raise or report as-is.
    """
    errors = getattr(exc, "errors", None)
    if isinstance(errors, list) and errors and all(isinstance(e, dict) for e in errors):
        return classify_graphql_error_dicts(errors)
    return None
