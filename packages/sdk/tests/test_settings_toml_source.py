"""SDK env-edge end-to-end TOML / env / dotenv loading via ``PipefyTomlConfigSource``.

The SDK value objects are env-free; env reading lives in ``pipefy_sdk.env``
(``load_sdk``) and ``pipefy_infra.env`` (``load_deployment``). These tests lock
the source precedence as observed through those loaders. The TOML-source mechanic
itself (sections, init-over-toml) is unit tested in the infra package.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pipefy_infra.env import load_deployment

from pipefy_sdk.env import load_sdk


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Clear PIPEFY_* env and point PIPEFY_CONFIG_FILE at the test tmpdir."""
    for key in list(os.environ):
        if key.startswith("PIPEFY_") or key in {"XDG_CONFIG_HOME", "APPDATA"}:
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PIPEFY_CONFIG_FILE", str(tmp_path / "config.toml"))


def test_field_name_keys_load_from_toml(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        """
        base_url = "https://staging.pipefy.com"
        default_webhook_name = "Test Hook"
        """,
    )
    deployment = load_deployment()
    assert deployment.base_url == "https://staging.pipefy.com"
    assert load_sdk(deployment)[3] == "Test Hook"


def test_env_wins_over_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(tmp_path / "config.toml", 'base_url = "https://from-toml.example"\n')
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://from-env.example")
    assert load_deployment().base_url == "https://from-env.example"


def test_dotenv_wins_over_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # chdir so ``env_file=".env"`` resolves to tmp_path. ``test_env_wins_over_toml``
    # does NOT cover this tier: a reorder sliding TOML between env and dotenv
    # would pass while silently flipping dotenv > toml precedence.
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / ".env", "PIPEFY_BASE_URL=https://from-dotenv.example\n")
    _write(tmp_path / "config.toml", 'base_url = "https://from-toml.example"\n')
    assert load_deployment().base_url == "https://from-dotenv.example"


def test_missing_file_uses_defaults() -> None:
    assert load_deployment().base_url == "https://app.pipefy.com"


def test_invalid_toml_raises_value_error_quoting_path(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", "base_url = \n")
    with pytest.raises(ValueError, match=str(path)):
        load_deployment()


def test_unknown_keys_ignored(tmp_path: Path) -> None:
    # Auth-only keys and arbitrary keys are silently dropped via ``extra="ignore"``.
    _write(
        tmp_path / "config.toml",
        """
        base_url = "https://staging.pipefy.com"
        completely_unrelated = 42
        """,
    )
    assert load_deployment().base_url == "https://staging.pipefy.com"


def test_base_url_is_single_sourced(tmp_path: Path) -> None:
    # A single ``base_url`` key feeds the one DeploymentConfig the edge injects;
    # the SDK endpoints derive from it, so host topology is single-sourced.
    _write(tmp_path / "config.toml", 'base_url = "https://shared.example"\n')
    deployment = load_deployment()
    assert deployment.base_url == "https://shared.example"
    assert load_sdk(deployment)[0].graphql_url == "https://shared.example/graphql"
