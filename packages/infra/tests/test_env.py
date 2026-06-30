"""Tests for ``pipefy_infra.env.load_deployment`` (the deployment-edge parser)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipefy_infra.deployment import DEFAULT_BASE_URL
from pipefy_infra.env import load_deployment


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """No host env / dotenv / config.toml leaks into the parse."""
    monkeypatch.delenv("PIPEFY_BASE_URL", raising=False)
    monkeypatch.delenv("PIPEFY_ALLOW_INSECURE_URLS", raising=False)
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(tmp_path / "absent.toml"))
    monkeypatch.chdir(tmp_path)


def test_defaults_to_production_when_nothing_set() -> None:
    deployment = load_deployment()
    assert deployment.base_url == DEFAULT_BASE_URL
    assert deployment.allow_insecure_urls is False


def test_reads_base_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://env.example.com")
    assert load_deployment().base_url == "https://env.example.com"


def test_flag_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://env.example.com")
    deployment = load_deployment(base_url="https://flag.example.com")
    assert deployment.base_url == "https://flag.example.com"


def test_flag_whitespace_is_trimmed_at_the_boundary() -> None:
    deployment = load_deployment(base_url="  https://flag.example.com  ")
    assert deployment.base_url == "https://flag.example.com"


def test_allow_insecure_flag_permits_loopback() -> None:
    deployment = load_deployment(base_url="http://127.0.0.1", allow_insecure_urls=True)
    assert deployment.allow_insecure_urls is True
    assert deployment.base_url == "http://127.0.0.1"


def test_invalid_base_url_raises() -> None:
    with pytest.raises(ValidationError):
        load_deployment(base_url="http://example.test")
