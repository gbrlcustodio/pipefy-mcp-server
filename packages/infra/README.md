# pipefy-infra

Schema-agnostic infrastructure helpers shared by `pipefy-sdk` and `pipefy-auth`. Sits at the bottom of the workspace dependency graph; depends only on stdlib + `pydantic` / `pydantic-settings`.

Adapter layer between Pipefy's application code (`pipefy-sdk`, `pipefy-auth`) and external concerns (filesystem, OS, network boundary). Each submodule owns one bounded context; the package root exposes only `__version__`.

## `pipefy_infra.config`

Pipefy on-disk configuration: where it lives and how it's read.

- `config_dir() -> Path`. Resolves the OS-appropriate config directory (`$XDG_CONFIG_HOME/pipefy` on POSIX, `%APPDATA%\pipefy` on Windows, falling back to `~/.config/pipefy` when `XDG_CONFIG_HOME` is unset).
- `config_file_path() -> Path`. Resolves the TOML file path, honouring the `PIPEFY_CONFIG_FILE` environment override.
- `PipefyTomlConfigSource`. A `pydantic-settings` source that loads top-level TOML keys from `config_file_path()`. The source knows nothing about specific field names; each consuming `BaseSettings` subclass filters via its own field definitions plus `extra="ignore"`.

```python
from pipefy_infra.config import config_dir, config_file_path, PipefyTomlConfigSource
```

## `pipefy_infra.security`

SSRF defenses on URLs destined for outbound HTTP. Three layered gates: shape regex, synchronous internal-IP check, asynchronous DNS-rebinding check.

- `URL_SHAPE_PATTERN`. Regex for `Field(..., pattern=...)` on URL settings fields.
- `validate_https_url(url, field_label, *, allow_insecure=False)`. Synchronous shape + private-IP gate. Enforces HTTPS unless `allow_insecure=True`.
- `assert_hostname_is_not_internal(hostname, *, context)`. Rejects localhost and literal IPs in private/loopback/link-local ranges.
- `assert_hostname_resolves_to_public_ips(hostname)`. Asynchronous DNS gate used right before issuing a request; defends against DNS-rebinding.

This is the **SSRF audit namespace**: import the module and call through it so every call site is greppable for audits, matching the stdlib idiom (`hmac.compare_digest`, `secrets.token_urlsafe`).

```python
from pipefy_infra import security

security.validate_https_url(url, "graphql_url", allow_insecure=False)
await security.assert_hostname_resolves_to_public_ips(host)
```

## `pipefy_infra.strings`

Generic string helpers (utility bucket; nothing here is bound to a single bounded context).

- `strip_str(value)`. Strips surrounding whitespace from string values, pass-through for non-strings. Primary use: inside `field_validator(..., mode="before")` bodies so a stray leading / trailing space from copy-paste does not trip the per-field `pattern` constraint.

```python
from pipefy_infra.strings import strip_str
```

## Field definitions

This package owns **no schema**. Field definitions live with the settings models that use them (`pipefy_auth.AuthSettings`, `pipefy_sdk.PipefySettings`).
