"""``pydantic-settings`` source that loads a flat TOML file at read time.

Schema-agnostic: returns the full top-level mapping. Each consuming
``BaseSettings`` subclass filters via its own field definitions plus
``extra="ignore"``. Resolves the file path lazily on every read so that
``PIPEFY_CONFIG_FILE`` changes during a test session take effect without
reconstructing the source.
"""

from __future__ import annotations

import tomllib
from typing import Any

from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from pipefy_infra.paths import config_file_path


class PipefyTomlConfigSource(PydanticBaseSettingsSource):
    """Load top-level TOML keys from :func:`config_file_path` as a settings source.

    Missing file → empty mapping (no error). Malformed TOML →
    ``ValueError`` quoting the file path, chained from the original
    ``tomllib.TOMLDecodeError`` so the parser context is preserved.
    """

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)

    def _read_toml(self) -> dict[str, Any]:
        path = config_file_path()
        if not path.is_file():
            return {}
        try:
            with path.open("rb") as handle:
                return tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            msg = f"invalid TOML in {path}"
            raise ValueError(msg) from exc

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        data = self._read_toml()
        if field_name in data:
            return data[field_name], field_name, False
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        # ``BaseSettings`` calls the source as a zero-arg callable expecting
        # the full mapping of field-name -> value. Pre-filter to known field
        # *names* (ignoring ``validation_alias``) so TOML stays strictly
        # field-name-keyed — env-only aliases like ``PIPEFY_TOKEN`` do not
        # double as TOML keys. Operators get one canonical TOML schema.
        data = self._read_toml()
        known = set(self.settings_cls.model_fields)
        return {key: value for key, value in data.items() if key in known}


__all__ = ["PipefyTomlConfigSource"]
