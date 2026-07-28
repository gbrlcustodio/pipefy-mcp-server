"""Platform-specific hints when OS keychain session storage fails after OAuth."""

from __future__ import annotations

import platform

from pipefy_infra.config import config_dir

from pipefy_cli._docs import DOCS_CLI_AUTH_REF

_ESCAPE_HATCH = (
    f"Alternatively set PIPEFY_KEYCHAIN_BACKEND=file or use a static "
    f"PIPEFY_TOKEN. See {DOCS_CLI_AUTH_REF}."
)

_LINUX_HINT = (
    "On headless Linux, ensure a Secret Service daemon "
    "(gnome-keyring, kwallet) is running. "
    f"{_ESCAPE_HATCH}"
)

_MACOS_HINT = (
    "macOS Keychain rejected the write (often errSecInvalidOwnerEdit, -25244: "
    "invalid attempt to change the owner of this item). Clear any stale entry "
    "with `pipefy auth logout`, then run `pipefy auth login` again from "
    "Terminal.app and click Always Allow if prompted. If logout cannot delete "
    "the item, run `security delete-generic-password -s pipefy` and retry. "
    f"{_ESCAPE_HATCH}"
)

_WINDOWS_HINT = (
    "On Windows, Credential Manager may reject the write. Run "
    "`pipefy auth login` once from an interactive Command Prompt or "
    "PowerShell window. "
    f"{_ESCAPE_HATCH}"
)

_GENERIC_HINT = (
    f"Run `pipefy auth status` to inspect the active backend, or see "
    f"{DOCS_CLI_AUTH_REF} for keychain troubleshooting."
)


def keychain_store_failure_hint(*, backend: str) -> str:
    """Return a remediation hint after ``store_session`` fails post-login."""
    if backend == "PlaintextKeyring":
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
