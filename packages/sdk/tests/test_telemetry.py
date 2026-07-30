"""Unit tests for the pure telemetry header builders."""

from __future__ import annotations

import pytest
from pipefy_infra.telemetry import auth_telemetry_headers

from pipefy_sdk.telemetry import telemetry_headers, telemetry_user_agent


@pytest.mark.unit
@pytest.mark.parametrize(
    ("surface", "expected"),
    [
        ("mcp", "pipefy-sdk/1.2.3 (mcp)"),
        ("cli", "pipefy-sdk/1.2.3 (cli)"),
        ("sdk", "pipefy-sdk/1.2.3 (sdk)"),
    ],
)
def test_user_agent_encodes_version_and_surface(surface, expected):
    assert telemetry_user_agent(surface=surface, version="1.2.3") == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("deployment", "expected"),
    [
        ("hosted", "pipefy-sdk/1.2.3 (mcp; hosted)"),
        ("local", "pipefy-sdk/1.2.3 (mcp; local)"),
    ],
)
def test_user_agent_appends_deployment_after_the_surface(deployment, expected):
    """A surface plus a deployment yields ``(<surface>; <deployment>)``.

    Both sides are labelled, so a bare ``(mcp)`` reads as a client older than the
    deployment axis rather than as ``local``.
    """
    assert (
        telemetry_user_agent(surface="mcp", deployment=deployment, version="1.2.3")
        == expected
    )


@pytest.mark.unit
def test_user_agent_omits_surface_when_none():
    """No surface yields a bare ``<product>/<version>``."""
    assert telemetry_user_agent(version="1.2.3") == "pipefy-sdk/1.2.3"
    assert telemetry_user_agent(version="1.2.3", surface=None) == "pipefy-sdk/1.2.3"


@pytest.mark.unit
def test_user_agent_omits_deployment_when_none():
    """No deployment leaves the surface parenthetical exactly as it was."""
    assert (
        telemetry_user_agent(surface="cli", version="1.2.3") == "pipefy-sdk/1.2.3 (cli)"
    )
    assert (
        telemetry_user_agent(surface="cli", version="1.2.3", deployment=None)
        == "pipefy-sdk/1.2.3 (cli)"
    )


@pytest.mark.unit
def test_user_agent_honors_product_override():
    assert (
        telemetry_user_agent(version="1.2.3", product="pipefy-auth")
        == "pipefy-auth/1.2.3"
    )


@pytest.mark.unit
def test_auth_telemetry_headers_use_pipefy_auth_and_auth_client_name():
    """OAuth headers identify the auth component, not an API surface."""
    assert auth_telemetry_headers(version="0.2.0-beta.4") == {
        "User-Agent": "pipefy-auth/0.2.0-beta.4",
        "X-Client-Name": "auth",
        "X-Client-Version": "0.2.0-beta.4",
    }


@pytest.mark.unit
def test_headers_carry_user_agent_and_parsed_split():
    headers = telemetry_headers(surface="mcp", version="0.2.0-beta.4")
    assert headers == {
        "User-Agent": "pipefy-sdk/0.2.0-beta.4 (mcp)",
        "X-Client-Name": "mcp",
        "X-Client-Version": "0.2.0-beta.4",
    }


@pytest.mark.unit
@pytest.mark.parametrize("deployment", ["hosted", "local"])
def test_headers_add_parsed_deployment_when_given(deployment):
    """``X-Client-Deployment`` repeats the deployment as a parsed field.

    The exact-dict assertion is the point: a consumer never has to match on the
    ``User-Agent`` string to split the two deployments of one surface.
    """
    headers = telemetry_headers(
        surface="mcp", version="0.2.0-beta.4", deployment=deployment
    )
    assert headers == {
        "User-Agent": f"pipefy-sdk/0.2.0-beta.4 (mcp; {deployment})",
        "X-Client-Name": "mcp",
        "X-Client-Version": "0.2.0-beta.4",
        "X-Client-Deployment": deployment,
    }


@pytest.mark.unit
def test_headers_omit_the_deployment_header_when_absent():
    """No deployment sends no ``X-Client-Deployment``, keeping the three-key shape.

    The CLI runs in exactly one place and passes no deployment, so its headers stay
    byte-identical to what they were before this axis existed.
    """
    assert telemetry_headers(surface="cli", version="0.2.0-beta.4") == {
        "User-Agent": "pipefy-sdk/0.2.0-beta.4 (cli)",
        "X-Client-Name": "cli",
        "X-Client-Version": "0.2.0-beta.4",
    }


@pytest.mark.unit
def test_headers_version_is_passed_in_not_looked_up():
    """The builder reports whatever version the caller supplies (no import of its own)."""
    headers = telemetry_headers(surface="sdk", version="9.9.9")
    assert headers["X-Client-Version"] == "9.9.9"
    assert headers["User-Agent"] == "pipefy-sdk/9.9.9 (sdk)"
