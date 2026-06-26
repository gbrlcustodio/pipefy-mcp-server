"""The domain / MCP settings models are pure value objects, not env readers.

Pins the boundary the edge-IO refactor established: env / file IO lives in the
``pipefy_infra`` readers and the app resolvers, never in the settings types. A
directly-constructed model ignores the environment entirely; only a reader picks
it up. Mirrors ``experiments/settings-injection/prototype_v2.py`` demo 1.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pipefy_auth import AuthSettings, JwtValidationSettings
from pipefy_infra.config import read_auth_env, read_client_env
from pipefy_sdk import ClientSettings
from pydantic_settings import BaseSettings

from pipefy_mcp.settings import McpSettings, ResourceServerSettings

_PURE_MODELS = [
    ClientSettings,
    AuthSettings,
    JwtValidationSettings,
    McpSettings,
    ResourceServerSettings,
]


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(tmp_path / "absent.toml"))
    for key in list(os.environ):
        if key.startswith("PIPEFY_") or key in {"XDG_CONFIG_HOME", "APPDATA"}:
            if key != "PIPEFY_CONFIG_FILE":
                monkeypatch.delenv(key, raising=False)


@pytest.mark.unit
@pytest.mark.parametrize("model", _PURE_MODELS)
def test_settings_models_are_not_env_readers(model: type) -> None:
    """No domain / MCP settings model subclasses ``pydantic_settings.BaseSettings``."""
    assert not issubclass(model, BaseSettings)


@pytest.mark.unit
def test_direct_auth_construction_ignores_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """``AuthSettings()`` keeps its default even with the env var set; the reader reads it."""
    monkeypatch.setenv("PIPEFY_AUTH_ISSUER_URL", "https://evil.example.com/realms/x")
    assert AuthSettings().issuer_url == "https://signin.pipefy.com/realms/pipefy"
    assert read_auth_env()["issuer_url"] == "https://evil.example.com/realms/x"


@pytest.mark.unit
def test_direct_client_construction_ignores_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``ClientSettings()`` keeps its default even with the env var set; the reader reads it."""
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://staging.example.com")
    assert ClientSettings().base_url == "https://app.pipefy.com"
    assert read_client_env()["base_url"] == "https://staging.example.com"
