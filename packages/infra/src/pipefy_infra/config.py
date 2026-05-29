"""Pipefy on-disk configuration: where it lives and how it's read.

Bounded context: the operator-editable Pipefy config file. Owns path
discovery (where the OS expects the config directory and the
``config.toml`` file to live) and the ``pydantic-settings`` source that
reads top-level TOML keys at settings construction.

Path discovery is intentionally hand-rolled. Adopting ``platformdirs``
would land config under ``~/Library/Application Support/pipefy`` on
macOS, breaking parity with the CLI tools operators expect to share that
location (``gh``, ``uv``, ``gcloud``).

The TOML source is schema-agnostic: it returns the full top-level mapping
filtered to the consuming ``BaseSettings`` subclass's field names
(env-only aliases like ``PIPEFY_TOKEN`` are intentionally not honoured as
TOML keys; operators get one canonical TOML schema).
"""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Any

from pydantic.fields import FieldInfo
from pydantic_settings import PydanticBaseSettingsSource

_CONFIG_FILE_ENV = "PIPEFY_CONFIG_FILE"


def config_dir() -> Path:
    """Resolve the shared Pipefy configuration directory.

    On POSIX honours ``XDG_CONFIG_HOME`` (per the XDG Base Directory
    Specification) and falls back to ``~/.config``. On Windows uses
    ``%APPDATA%`` with a ``~/AppData/Roaming`` fallback. Returns the path
    unconditionally; the directory may not yet exist.
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
    unconditionally; the file may not yet exist; consumers must tolerate that.
    """
    override = os.environ.get(_CONFIG_FILE_ENV)
    if override:
        return Path(override)
    return config_dir() / "config.toml"


class PipefyTomlConfigSource(PydanticBaseSettingsSource):
    """Load top-level TOML keys from :func:`config_file_path` as a settings source.

    Missing file produces an empty mapping (no error). Malformed TOML
    produces ``ValueError`` quoting the file path, chained from the
    original ``tomllib.TOMLDecodeError`` so the parser context is preserved.
    """

    _cache: dict[str, Any] | None = None

    def _data(self) -> dict[str, Any]:
        # Pydantic-settings constructs a fresh source per ``BaseSettings.__init__``,
        # so caching on the instance scopes to "one settings construction"; the
        # lazy behaviour the tests exercise (env change between constructions)
        # still works because each construction gets a new source instance.
        if self._cache is not None:
            return self._cache
        path = config_file_path()
        if not path.is_file():
            self._cache = {}
            return self._cache
        try:
            with path.open("rb") as handle:
                raw = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            msg = f"invalid TOML in {path}"
            raise ValueError(msg) from exc
        known = set(self.settings_cls.model_fields)
        self._cache = {key: value for key, value in raw.items() if key in known}
        return self._cache

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        del field  # signature dictated by ``PydanticBaseSettingsSource``
        data = self._data()
        if field_name in data:
            return data[field_name], field_name, False
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        return self._data()


__all__ = ["PipefyTomlConfigSource", "config_dir", "config_file_path"]
