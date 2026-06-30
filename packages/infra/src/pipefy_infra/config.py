"""Pipefy on-disk configuration: the ``pydantic-settings`` TOML source.

Bounded context: the operator-editable Pipefy config file. Owns the
``pydantic-settings`` source that reads top-level TOML keys at settings
construction. Path discovery (``config_dir`` / ``config_file_path``) lives in
:mod:`pipefy_infra.paths` (stdlib only); it is re-exported here for the consumers
that read TOML, but path-only consumers should import it from there to stay off
the ``pydantic-settings`` import path.

The TOML source is schema-agnostic: it returns the full top-level mapping
filtered to the consuming ``BaseSettings`` subclass's field names
(env-only aliases like ``PIPEFY_TOKEN`` are intentionally not honoured as
TOML keys; operators get one canonical TOML schema).
"""

from __future__ import annotations

import tomllib
from typing import Any

from pydantic.fields import FieldInfo
from pydantic_settings import PydanticBaseSettingsSource

from pipefy_infra.paths import config_dir, config_file_path


class PipefyTomlConfigSource(PydanticBaseSettingsSource):
    """Load TOML keys from :func:`config_file_path` as a settings source.

    Reads top-level keys by default; pass ``section`` to read a named sub-table
    instead (so readers whose bare field names would collide in one flat
    namespace, e.g. two ``issuer_url`` fields, each get their own ``[section]``).

    Missing file produces an empty mapping (no error). Malformed TOML, or a
    ``section`` key whose value is not a table, produces ``ValueError`` quoting
    the file path; the malformed-TOML case is chained from the original
    ``tomllib.TOMLDecodeError`` so the parser context is preserved.
    """

    _cache: dict[str, Any] | None = None

    def __init__(
        self,
        settings_cls: type[Any],
        section: str | None = None,
    ) -> None:
        super().__init__(settings_cls)
        self._section = section

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
        if self._section is not None:
            section_value = raw.get(self._section, {})
            if not isinstance(section_value, dict):
                msg = f"invalid TOML in {path}: [{self._section}] must be a table"
                raise ValueError(msg)
            raw = section_value
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
