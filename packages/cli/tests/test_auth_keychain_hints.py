from __future__ import annotations

import platform

import pytest

from pipefy_cli.commands import auth_keychain_hints as hints


@pytest.mark.parametrize(
    ("system", "expected_fragment"),
    [
        ("Darwin", "errSecParam"),
        ("Darwin", "Terminal.app"),
        ("Darwin", "Always Allow"),
        ("Linux", "Secret Service"),
        ("Windows", "Credential Manager"),
        ("FreeBSD", "pipefy auth status"),
    ],
)
def test_keychain_hint_for_platform(
    monkeypatch: pytest.MonkeyPatch, system: str, expected_fragment: str
) -> None:
    monkeypatch.setattr(platform, "system", lambda: system)
    hint = hints.keychain_store_failure_hint(backend="Keyring")
    assert expected_fragment in hint
    if system == "Darwin":
        assert "Secret Service" not in hint


def test_plaintext_backend_hint_ignores_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    hint = hints.keychain_store_failure_hint(backend="PlaintextKeyring")
    assert "config directory is writable" in hint
    assert "errSecParam" not in hint
