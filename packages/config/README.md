# pipefy-config

Schema-agnostic configuration helpers shared by `pipefy-sdk` and `pipefy-auth`.

Exposes three primitives:

- `config_dir() -> Path` — resolves the on-disk Pipefy config directory
  (`$XDG_CONFIG_HOME/pipefy` on POSIX, `%APPDATA%\pipefy` on Windows, falling
  back to `~/.config/pipefy` when `XDG_CONFIG_HOME` is unset).
- `config_file_path() -> Path` — resolves the TOML file path, honouring the
  `PIPEFY_CONFIG_FILE` environment override.
- `PipefyTomlConfigSource` — a `pydantic-settings` source that loads top-level
  TOML keys from `config_file_path()`. The source knows nothing about specific
  field names; each consuming `BaseSettings` subclass filters via its own field
  definitions plus `extra="ignore"`.

This package owns no schema. Field definitions live with the settings models
that use them (`pipefy_auth.AuthSettings`, `pipefy_sdk.PipefySettings`).
