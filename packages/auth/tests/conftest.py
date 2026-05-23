"""Pytest fixtures for ``pipefy-auth``."""

from __future__ import annotations

from pathlib import Path

import keyring
import keyring.backend
import pytest


@pytest.fixture(autouse=True)
def _isolate_refresh_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the cross-process refresh lock into the test's tmp dir.

    Without this autouse, any test exercising ``ensure_fresh_session`` would
    create ``~/.config/pipefy/refresh.lock`` on the developer's machine.
    """
    monkeypatch.setattr(
        "pipefy_auth.refresh.refresh_lock_path",
        lambda: tmp_path / "refresh.lock",
    )


class InMemoryKeyring(keyring.backend.KeyringBackend):
    """In-memory keyring backend that mirrors the real-world ``delete_password``
    contract (raises ``PasswordDeleteError`` when the entry is missing)."""

    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        from keyring.errors import PasswordDeleteError

        if (service, username) not in self._store:
            raise PasswordDeleteError(f"no entry for {service}/{username}")
        del self._store[(service, username)]


@pytest.fixture
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> InMemoryKeyring:
    """Patch the ``keyring`` module surface our storage code uses."""

    fake = InMemoryKeyring()
    monkeypatch.setattr(keyring, "_keyring_backend", fake, raising=False)
    monkeypatch.setattr(keyring, "get_keyring", lambda: fake)
    monkeypatch.setattr(keyring, "set_password", fake.set_password)
    monkeypatch.setattr(keyring, "get_password", fake.get_password)
    monkeypatch.setattr(keyring, "delete_password", fake.delete_password)
    return fake
