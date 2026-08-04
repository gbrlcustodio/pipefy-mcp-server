"""Client-identifying telemetry headers for outbound Pipefy API requests.

Re-exported from :mod:`pipefy_infra.telemetry` so the SDK and the auth package
share one ``User-Agent`` format.
"""

from __future__ import annotations

from pipefy_infra.telemetry import (
    ClientDeployment,
    ClientSurface,
    telemetry_headers,
    telemetry_user_agent,
)

__all__ = [
    "ClientDeployment",
    "ClientSurface",
    "telemetry_headers",
    "telemetry_user_agent",
]
