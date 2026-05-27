# pipefy-infra

Schema-agnostic infrastructure helpers shared by `pipefy-sdk` and `pipefy-auth`. Sits at the bottom of the workspace dependency graph; depends only on stdlib + `pydantic` / `pydantic-settings`.

Adapter layer between Pipefy's application code (`pipefy-sdk`, `pipefy-auth`) and external concerns (filesystem, OS, network boundary). Two concerns:

## Configuration

- `config_dir() -> Path` — resolves the on-disk Pipefy config directory (`$XDG_CONFIG_HOME/pipefy` on POSIX, `%APPDATA%\pipefy` on Windows, falling back to `~/.config/pipefy` when `XDG_CONFIG_HOME` is unset).
- `config_file_path() -> Path` — resolves the TOML file path, honouring the `PIPEFY_CONFIG_FILE` environment override.
- `PipefyTomlConfigSource` — a `pydantic-settings` source that loads top-level TOML keys from `config_file_path()`. The source knows nothing about specific field names; each consuming `BaseSettings` subclass filters via its own field definitions plus `extra="ignore"`.

## URL SSRF gates

- `validate_https_service_endpoint_url(url, field_label, *, allow_insecure=False)` — synchronous shape gate used at settings construction.
- `assert_hostname_is_not_internal(hostname, *, context)` — rejects localhost and literal IPs in private/loopback/link-local ranges.
- `assert_hostname_resolves_to_public_ips(hostname)` — asynchronous DNS gate used right before issuing a request; defends against DNS-rebinding.

This package owns **no schema**. Field definitions live with the settings models that use them (`pipefy_auth.AuthSettings`, `pipefy_sdk.PipefySettings`).
