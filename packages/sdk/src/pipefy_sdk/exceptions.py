from __future__ import annotations

# Typed SDK errors for future service-layer raises (Task 2.5 placeholder); unused until callers adopt them.


class PipefyError(Exception):
    """Base class for Pipefy SDK errors."""


class PipefyAPIError(PipefyError):
    """Raised when the Pipefy GraphQL API returns an error payload."""
