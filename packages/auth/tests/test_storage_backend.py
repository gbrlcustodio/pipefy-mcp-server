"""Coverage for ``configure_keychain_backend`` (env-driven keyring swap)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import keyring
import pytest
from keyrings.alt.file import PlaintextKeyring

from pipefy_auth.storage import configure_keychain_backend


@pytest.fixture
def _isolated_keyring() -> Iterator[None]:
    """Reset the module-level keyring after each test (don't leak into siblings)."""
    original = keyring.get_keyring()
    yield
    keyring.set_keyring(original)


@pytest.fixture
def config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``config_dir()`` at ``tmp_path`` so file-backend writes stay sandboxed."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


@pytest.mark.unit
def test_file_backend_swaps_to_plaintext_keyring(
    _isolated_keyring: None,
    config_home: Path,
) -> None:
    """``configure_keychain_backend('file')`` installs a ``PlaintextKeyring`` under ``config_dir()``."""
    configure_keychain_backend("file")

    backend = keyring.get_keyring()
    assert isinstance(backend, PlaintextKeyring)
    assert backend.file_path == str(config_home / "pipefy" / "keyring.cfg")


@pytest.mark.unit
def test_auto_backend_is_a_noop(
    _isolated_keyring: None,
) -> None:
    """``configure_keychain_backend('auto')`` leaves the active backend untouched."""
    before = keyring.get_keyring()
    configure_keychain_backend("auto")
    assert keyring.get_keyring() is before


@pytest.mark.unit
def test_file_backend_is_idempotent(
    _isolated_keyring: None,
    config_home: Path,
) -> None:
    """Calling ``configure_keychain_backend('file')`` twice converges on the same backend."""
    configure_keychain_backend("file")
    first = keyring.get_keyring()
    configure_keychain_backend("file")
    second = keyring.get_keyring()

    assert isinstance(first, PlaintextKeyring)
    assert isinstance(second, PlaintextKeyring)
    assert first.file_path == second.file_path


@pytest.mark.unit
def test_file_backend_round_trip_writes_under_config_dir(
    _isolated_keyring: None,
    config_home: Path,
) -> None:
    """Once swapped, ``set_password`` / ``get_password`` go through the file backend."""
    configure_keychain_backend("file")
    keyring.set_password("pipefy-test", "user", "secret-value")

    backing_file = config_home / "pipefy" / "keyring.cfg"
    assert backing_file.exists()
    assert keyring.get_password("pipefy-test", "user") == "secret-value"
