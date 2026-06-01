"""Platform-specific hints when OS keychain session storage fails after OAuth."""

from __future__ import annotations

import platform

from pipefy_cli._docs import DOCS_CLI_AUTH_REF

_LINUX_HINT = (
    "On headless Linux, ensure a Secret Service daemon "
    "(gnome-keyring, kwallet) is running, set "
    "PIPEFY_KEYCHAIN_BACKEND=file to use a plaintext file backend, "
    "or use a static PIPEFY_TOKEN."
)

_MACOS_HINT = (
    "This is usually macOS denying the calling subprocess access to the "
    "keychain ACL prompt (errSecParam, -25244). Run `pipefy auth login` once "
    "from a regular Terminal.app session and click Always Allow when macOS "
    "prompts; subsequent runs (including agent / IDE integrations) will write "
    "without prompting."
)

_WINDOWS_HINT = (
    "On Windows, Credential Manager may block writes from non-interactive "
    "callers. Run `pipefy auth login` once from an interactive Command Prompt "
    "or PowerShell window, or set PIPEFY_KEYCHAIN_BACKEND=file, or use a "
    "static PIPEFY_TOKEN."
)

_GENERIC_HINT = (
    f"Run `pipefy auth status` to inspect the active backend, or see "
    f"{DOCS_CLI_AUTH_REF} for keychain troubleshooting."
)


def keychain_store_failure_hint(*, backend: str) -> str:
    """Return a remediation hint after ``store_session`` fails post-login."""
    if backend == "PlaintextKeyring":
        from pipefy_infra.config import config_dir

        return (
            f"Ensure the config directory is writable ({config_dir()}), "
            "or use a static PIPEFY_TOKEN."
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
