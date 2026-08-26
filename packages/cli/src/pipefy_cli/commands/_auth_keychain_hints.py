"""Platform-specific hints when OS keychain session storage fails after OAuth."""

from __future__ import annotations

import platform

from pipefy_infra.config import config_dir

from pipefy_cli._docs import DOCS_CLI_AUTH_REF

_ESCAPE_HATCH = (
    f"Alternatively set PIPEFY_KEYCHAIN_BACKEND=encrypted (macOS/Windows, "
    f"OS-encrypted file), PIPEFY_KEYCHAIN_BACKEND=file (plaintext), or use a "
    f"static PIPEFY_TOKEN. See {DOCS_CLI_AUTH_REF}."
)

_LINUX_HINT = (
    "On headless Linux, ensure a Secret Service daemon "
    "(gnome-keyring, kwallet) is running. "
    f"{_ESCAPE_HATCH}"
)

_MACOS_HINT = (
    "macOS Keychain rejected the write (often errSecInvalidOwnerEdit, -25244: "
    "invalid attempt to change the owner of this item). Prefer "
    "`PIPEFY_KEYCHAIN_BACKEND=encrypted` so refresh does not re-prompt unsigned "
    "Python interpreters. Or clear the entry with `pipefy auth logout`; if that "
    "fails, remove it directly with `security delete-generic-password -s pipefy`. "
    "Then run `pipefy auth login` again from Terminal.app and click Always Allow "
    f"if prompted. {_ESCAPE_HATCH}"
)

_WINDOWS_HINT = (
    "On Windows, Credential Manager may reject the write (including WinError "
    "1783 when the session blob exceeds the credential size cap). Set "
    "`PIPEFY_KEYCHAIN_BACKEND=encrypted` (DPAPI-wrapped file, no blob cap) or "
    "run `pipefy auth login` once from an interactive Command Prompt or "
    f"PowerShell window. {_ESCAPE_HATCH}"
)

_GENERIC_HINT = (
    f"Run `pipefy auth status` to inspect the active backend, or see "
    f"{DOCS_CLI_AUTH_REF} for keychain troubleshooting."
)


_FILE_BACKED_BACKENDS = frozenset({"PlaintextKeyring", "EncryptedFileKeyring"})


def keychain_store_failure_hint(*, backend: str) -> str:
    """Return a remediation hint after ``store_session`` fails post-login."""
    if backend in _FILE_BACKED_BACKENDS:
        return (
            f"Ensure the config directory is writable ({config_dir()}), "
            f"or use a static PIPEFY_TOKEN. See {DOCS_CLI_AUTH_REF}."
        )
    return _keychain_hint_for_platform()


def _keychain_hint_for_platform() -> str:
    system = platform.system()
    if system == "Darwin":
        return _MACOS_HINT
    if system == "Linux":
        return _LINUX_HINT
    if system == "Windows":
        return _WINDOWS_HINT
    return _GENERIC_HINT


__all__ = ["keychain_store_failure_hint"]
