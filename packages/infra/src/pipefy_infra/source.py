"""``pydantic-settings`` source that loads a flat TOML file at read time.

Schema-agnostic: returns the full top-level mapping filtered to the consuming
``BaseSettings`` subclass's field *names* (env-only aliases like
``PIPEFY_TOKEN`` are intentionally not honoured as TOML keys). Resolves the
file path lazily on first access so that ``PIPEFY_CONFIG_FILE`` changes
between settings constructions take effect without reconstructing the source.
"""

from __future__ import annotations

import tomllib
from typing import Any

from pydantic.fields import FieldInfo
from pydantic_settings import PydanticBaseSettingsSource

from pipefy_infra.paths import config_file_path


class PipefyTomlConfigSource(PydanticBaseSettingsSource):
    """Load top-level TOML keys from :func:`config_file_path` as a settings source.

    Missing file → empty mapping (no error). Malformed TOML →
    ``ValueError`` quoting the file path, chained from the original
    ``tomllib.TOMLDecodeError`` so the parser context is preserved.
    """

    _cache: dict[str, Any] | None = None

    def _data(self) -> dict[str, Any]:
        # Pydantic-settings constructs a fresh source per ``BaseSettings.__init__``,
        # so caching on the instance scopes to "one settings construction" — the
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
        # Filter to known field *names*, ignoring ``validation_alias`` — env-only
        # aliases like ``PIPEFY_TOKEN`` do not double as TOML keys. Operators
        # get one canonical TOML schema.
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


__all__ = ["PipefyTomlConfigSource"]
