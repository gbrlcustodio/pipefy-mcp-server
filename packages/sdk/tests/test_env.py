"""Unit tests for ``pipefy_sdk.env.load_sdk`` (the SDK's env parser)."""

from __future__ import annotations

import pytest
from pipefy_infra.deployment import DeploymentConfig

from pipefy_sdk.env import load_sdk


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """No host env / dotenv / config.toml leaks into the knob parse."""
    monkeypatch.delenv("PIPEFY_GQL_REUSE_FETCHED_GRAPHQL_SCHEMA", raising=False)
    monkeypatch.delenv("PIPEFY_DEFAULT_WEBHOOK_NAME", raising=False)
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(tmp_path / "absent.toml"))
    monkeypatch.chdir(tmp_path)


@pytest.mark.unit
def test_derives_endpoints_from_deployment() -> None:
    deployment = DeploymentConfig(base_url="https://staging.example.com")
    endpoints, allow_insecure, reuse, webhook_name = load_sdk(deployment)
    assert endpoints.graphql_url == "https://staging.example.com/graphql"
    assert endpoints.interfaces_graphql_url == (
        "https://staging.example.com/graphql/interfaces"
    )
    assert endpoints.internal_api_url == "https://staging.example.com/internal_api"


@pytest.mark.unit
def test_forwards_posture_off_deployment() -> None:
    deployment = DeploymentConfig(base_url="http://127.0.0.1", allow_insecure_urls=True)
    _endpoints, allow_insecure, _reuse, _name = load_sdk(deployment)
    assert allow_insecure is True


@pytest.mark.unit
def test_knob_defaults() -> None:
    _endpoints, _posture, reuse, webhook_name = load_sdk(DeploymentConfig())
    assert reuse is False
    assert webhook_name == "Pipefy Webhook"


@pytest.mark.unit
def test_reads_knobs_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPEFY_GQL_REUSE_FETCHED_GRAPHQL_SCHEMA", "true")
    monkeypatch.setenv("PIPEFY_DEFAULT_WEBHOOK_NAME", "Custom Hook")
    _endpoints, _posture, reuse, webhook_name = load_sdk(DeploymentConfig())
    assert reuse is True
    assert webhook_name == "Custom Hook"
