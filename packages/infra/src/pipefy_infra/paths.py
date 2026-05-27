"""On-disk path discovery for Pipefy's shared configuration directory.

The directory hosts the operator-edited ``config.toml`` plus sibling artifacts
owned by other packages (e.g. ``pipefy_auth.locks.refresh_lock_path`` writes
``refresh.lock`` here). Discovery is intentionally hand-rolled — adopting
``platformdirs`` would land config under ``~/Library/Application Support/pipefy``
on macOS, breaking parity with the CLI tools operators expect to share that
location (``gh``, ``uv``, ``gcloud``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_CONFIG_FILE_ENV = "PIPEFY_CONFIG_FILE"


def config_dir() -> Path:
    """Resolve the shared Pipefy configuration directory.

    On POSIX honours ``XDG_CONFIG_HOME`` (per the XDG Base Directory
    Specification) and falls back to ``~/.config``. On Windows uses
    ``%APPDATA%`` with a ``~/AppData/Roaming`` fallback. Returns the path
    unconditionally — the directory may not yet exist.
    """
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "pipefy"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "pipefy"


def config_file_path() -> Path:
    """Resolve the operator-editable ``config.toml`` path.

    Honours the ``PIPEFY_CONFIG_FILE`` env override (useful for tests, ops
    automation, and multi-environment workflows). Returns the path
    unconditionally — the file may not yet exist; consumers must tolerate that.
    """
    override = os.environ.get(_CONFIG_FILE_ENV)
    if override:
        return Path(override)
    return config_dir() / "config.toml"


__all__ = ["config_dir", "config_file_path"]
