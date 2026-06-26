"""SDK client env/file plumbing via ``read_client_env``, end-to-end into ``ClientSettings``.

``ClientSettings`` is a pure value object that reads no env / ``.env`` / TOML;
that IO is ``pipefy_infra.config.read_client_env``'s concern. These tests drive
the reader (which the SDK package already depends on) and assert the raw mapping,
then feed it into ``ClientSettings(**read_client_env())`` to lock the end-to-end
path the application edge uses.

The reader's own unit coverage (empty env, exclude_unset, flag override + strip,
TOML pickup) lives in
``packages/infra/tests/test_edge_readers.py``; this file adds the precedence
tiers (env > dotenv > toml) and the SDK-shaped TOML keys, plus the value-object
hand-off. The removed ``org_id`` key moved to the CLI composite
(``packages/cli/tests/test_config.py``).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pipefy_infra.config import read_client_env

from pipefy_sdk.settings import ClientSettings


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
    raw = read_client_env()
    assert raw == {
        "base_url": "https://staging.pipefy.com",
        "default_webhook_name": "Test Hook",
    }
    settings = ClientSettings(**raw)
    assert settings.base_url == "https://staging.pipefy.com"
    assert settings.default_webhook_name == "Test Hook"


def test_env_wins_over_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(tmp_path / "config.toml", 'base_url = "https://from-toml.example"\n')
    monkeypatch.setenv("PIPEFY_BASE_URL", "https://from-env.example")
    assert read_client_env()["base_url"] == "https://from-env.example"


def test_dotenv_wins_over_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # chdir so ``env_file=".env"`` resolves to tmp_path. ``test_env_wins_over_toml``
    # does NOT cover this tier: a reorder sliding TOML between env and dotenv
    # would pass while silently flipping dotenv > toml precedence.
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / ".env", "PIPEFY_BASE_URL=https://from-dotenv.example\n")
    _write(tmp_path / "config.toml", 'base_url = "https://from-toml.example"\n')
    assert read_client_env()["base_url"] == "https://from-dotenv.example"


def test_flag_override_wins_over_toml(tmp_path: Path) -> None:
    # The ``base_url`` flag (e.g. CLI ``--base-url``) overrides env / file.
    _write(tmp_path / "config.toml", 'base_url = "https://from-toml.example"\n')
    assert (
        read_client_env(base_url="https://from-flag.example")["base_url"]
        == "https://from-flag.example"
    )


def test_missing_file_yields_empty_mapping_and_value_object_defaults() -> None:
    # No file → reader returns nothing → the value object supplies every default.
    assert read_client_env() == {}
    settings = ClientSettings(**read_client_env())
    assert settings.base_url == "https://app.pipefy.com"


def test_invalid_toml_raises_value_error_quoting_path(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", "base_url = \n")
    with pytest.raises(ValueError, match=str(path)):
        read_client_env()


def test_unknown_keys_ignored(tmp_path: Path) -> None:
    # Auth-only keys (e.g. ``issuer_url``) and arbitrary keys are dropped by the
    # client reader (``extra="ignore"`` + its own field set).
    _write(
        tmp_path / "config.toml",
        """
        base_url = "https://staging.pipefy.com"
        issuer_url = "https://signin-staging.pipefy.com/realms/pipefy"
        completely_unrelated = 42
        """,
    )
    assert read_client_env() == {"base_url": "https://staging.pipefy.com"}


def test_shared_base_url_loads_into_both_readers(tmp_path: Path) -> None:
    # A single ``base_url`` key in TOML feeds the client reader; the auth model
    # gets the same host root via the caller-injected ``oauth_token_url``, not by
    # reading ``base_url`` itself (see ``read_auth_env``). Assert the client side
    # here; the injection is covered by the auth / edge-reader tests.
    _write(tmp_path / "config.toml", 'base_url = "https://shared.example"\n')
    assert read_client_env()["base_url"] == "https://shared.example"
    assert ClientSettings(**read_client_env()).base_url == "https://shared.example"
