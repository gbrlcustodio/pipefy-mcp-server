"""Schema-agnostic infrastructure helpers shared by ``pipefy_sdk`` and ``pipefy_auth``.

The package root exposes only ``__version__``; consumers import from the
submodule that names the concern.

* :mod:`pipefy_infra.config`: Pipefy on-disk configuration. Path
  discovery (:func:`~pipefy_infra.config.config_dir`,
  :func:`~pipefy_infra.config.config_file_path`) and the
  ``pydantic-settings`` source that reads the operator-editable TOML
  file (:class:`~pipefy_infra.config.PipefyTomlConfigSource`). The source
  holds **no** field definitions; each consuming ``BaseSettings`` filters
  via its own ``Field`` declarations plus ``extra="ignore"``.
* :mod:`pipefy_infra.security`: SSRF defenses on URLs destined for
  outbound HTTP. Three layered gates: ``URL_SHAPE_PATTERN`` (regex for
  ``Field(pattern=...)``), :func:`~pipefy_infra.security.validate_https_url`
  (synchronous shape + private-IP gate), and
  :func:`~pipefy_infra.security.assert_hostname_resolves_to_public_ips`
  (asynchronous DNS-rebinding gate). Import the module itself
  (``from pipefy_infra import security``) and call through it
  (``security.validate_https_url(...)``) so every call site is greppable
  for SSRF audits (same idiom as stdlib ``hmac.compare_digest`` /
  ``secrets.token_urlsafe``).
* :mod:`pipefy_infra.strings`: generic string helpers (utility bucket).
  Current sole inhabitant is :func:`~pipefy_infra.strings.strip_str`,
  used inside ``field_validator(..., mode="before")`` bodies to strip
  surrounding whitespace before per-field ``pattern`` constraints fire.

Anything in these submodules must run on stdlib + ``pydantic`` /
``pydantic-settings`` only. No httpx, no keyring, no gql. The package sits
at the bottom of the workspace dependency graph.
"""

from __future__ import annotations

__version__ = "0.2.0-beta.1"

__all__ = ["__version__"]
