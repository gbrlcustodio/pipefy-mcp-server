from __future__ import annotations

# Typed SDK errors for gradual service-layer migration; not all call sites raise these yet.


class PipefyError(Exception):
    """Base class for Pipefy SDK errors."""


class PipefyAPIError(PipefyError):
    """Raised when the Pipefy GraphQL API returns an error payload."""


class MalformedPipefyResponseError(PipefyAPIError):
    """Raised when Pipefy accepts a mutation but omits a field the caller needs.

    Separate from :class:`PipefyAPIError` because the write may already have
    landed: the API reported no error, it just did not echo back what it did.
    Callers must not present this as a plain failure or retry it blindly.
    """


class PortalPermissionError(ValueError):
    """Raised when a portal Interfaces operation fails with PERMISSION_DENIED."""
