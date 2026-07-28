from __future__ import annotations

import platform

import pytest

from pipefy_cli.commands import _auth_keychain_hints as hints


@pytest.mark.parametrize(
    ("system", "required", "forbidden"),
    [
        (
            "Darwin",
            [
                "errSecInvalidOwnerEdit",
                "pipefy auth logout",
                "Not signed in. Nothing to do.",
                "security delete-generic-password -s pipefy",
                "Terminal.app",
                "Always Allow",
                "PIPEFY_KEYCHAIN_BACKEND=file",
                "PIPEFY_TOKEN",
                "docs/cli/auth.md",
            ],
            ["Secret Service", "errSecParam"],
        ),
        (
            "Linux",
            [
                "Secret Service",
                "PIPEFY_KEYCHAIN_BACKEND=file",
                "PIPEFY_TOKEN",
                "docs/cli/auth.md",
            ],
            ["Terminal.app", "Credential Manager"],
        ),
        (
            "Windows",
            [
                "Credential Manager",
                "PIPEFY_KEYCHAIN_BACKEND=file",
                "PIPEFY_TOKEN",
                "docs/cli/auth.md",
            ],
            ["Secret Service", "Terminal.app"],
        ),
        ("FreeBSD", ["pipefy auth status", "docs/cli/auth.md"], []),
    ],
)
def test_keychain_hint_for_platform(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    required: list[str],
    forbidden: list[str],
) -> None:
    monkeypatch.setattr(platform, "system", lambda: system)
    hint = hints.keychain_store_failure_hint(backend="Keyring")
    for fragment in required:
        assert fragment in hint
    for fragment in forbidden:
        assert fragment not in hint


def test_plaintext_backend_hint_ignores_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    hint = hints.keychain_store_failure_hint(backend="PlaintextKeyring")
    assert "config directory is writable" in hint
    assert "errSecInvalidOwnerEdit" not in hint
    assert "docs/cli/auth.md" in hint
