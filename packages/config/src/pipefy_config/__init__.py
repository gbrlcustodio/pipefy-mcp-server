"""Schema-agnostic configuration helpers shared by ``pipefy_sdk`` and ``pipefy_auth``.

Owns the on-disk Pipefy config directory discovery and a ``pydantic-settings``
source that reads a flat-namespace TOML file. Holds **no** field definitions:
each consuming ``BaseSettings`` subclass filters the TOML mapping through its
own ``Field`` declarations plus ``extra="ignore"``. Adding a new auth or SDK
field never touches this package.
"""

from __future__ import annotations

__version__ = "0.2.0-beta.1"

from pipefy_config.paths import config_dir, config_file_path
from pipefy_config.source import PipefyTomlConfigSource

__all__ = [
    "PipefyTomlConfigSource",
    "__version__",
    "config_dir",
    "config_file_path",
]
