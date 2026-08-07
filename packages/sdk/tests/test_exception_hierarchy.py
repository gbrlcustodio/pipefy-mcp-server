"""The SDK error hierarchy consumers catch against.

``PipefyError`` is the documented root, so ``except PipefyError`` has to catch
the failures the SDK actually raises. It did not: ``PipefyGraphQLError``, the
type every GraphQL failure arrives as, subclassed ``Exception`` directly, so the
root caught nothing a caller would ever see. These pin the parentage.

``PortalPermissionError`` is deliberately outside the hierarchy; see its test
below.
"""

from __future__ import annotations

from pipefy_sdk import PipefyAPIError, PipefyError, PipefyGraphQLError
from pipefy_sdk.exceptions import PortalPermissionError


def test_graphql_error_is_an_api_error() -> None:
    """A GraphQL ``errors`` payload is the API reporting a failure."""
    assert issubclass(PipefyGraphQLError, PipefyAPIError)


def test_graphql_error_is_catchable_as_the_root() -> None:
    """``except PipefyError`` catches what the SDK raises, not just what it declares."""
    assert issubclass(PipefyGraphQLError, PipefyError)


def test_api_error_is_rooted() -> None:
    assert issubclass(PipefyAPIError, PipefyError)


def test_raised_graphql_error_is_caught_by_the_root() -> None:
    """The parentage holds for an instance, not only for the classes."""
    try:
        raise PipefyGraphQLError([{"message": "denied"}])
    except PipefyError as exc:
        assert isinstance(exc, PipefyGraphQLError)
        assert exc.errors == [{"message": "denied"}]
    else:  # pragma: no cover - the raise above always fires
        raise AssertionError("PipefyGraphQLError escaped except PipefyError")


def test_portal_permission_error_stays_a_value_error() -> None:
    """Deliberately outside the hierarchy, and load-bearing.

    The CLI runners map ``ValueError`` to exit code 2 and ``PipefyError`` to exit
    1. Portal permission denials exit 2 because of this parentage, which
    ``test_portal_sub_portal_detach_permission_error_still_exits_2`` pins from the
    CLI side. Rooting this under ``PipefyError`` would silently move it to 1.
    """
    assert issubclass(PortalPermissionError, ValueError)
    assert not issubclass(PortalPermissionError, PipefyError)
