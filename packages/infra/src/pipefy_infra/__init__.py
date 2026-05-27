"""Schema-agnostic infrastructure helpers shared by ``pipefy_sdk`` and ``pipefy_auth``.

Two concerns:

* **Configuration** — on-disk Pipefy config directory discovery
  (:func:`config_dir`, :func:`config_file_path`) and a ``pydantic-settings``
  source (:class:`PipefyTomlConfigSource`) that reads a flat-namespace TOML
  file. Holds **no** field definitions: each consuming ``BaseSettings``
  subclass filters the TOML mapping through its own ``Field`` declarations
  plus ``extra="ignore"``. Adding a new auth or SDK field never touches this
  package.
* **URL SSRF gates** — :func:`validate_https_service_endpoint_url`,
  :func:`assert_hostname_is_not_internal`, and
  :func:`assert_hostname_resolves_to_public_ips`. Both SDK and Auth call
  these on every operator-supplied or remotely-discovered URL (OIDC issuer,
  GraphQL endpoint, internal API, webhook target).

Anything imported here must run on stdlib + ``pydantic`` / ``pydantic-settings``
only — no httpx, no keyring, no gql. The package sits at the bottom of the
workspace dependency graph.
"""

from __future__ import annotations

__version__ = "0.2.0-beta.1"

from pipefy_infra.paths import config_dir, config_file_path
from pipefy_infra.source import PipefyTomlConfigSource
from pipefy_infra.url_ssrf import (
    assert_hostname_is_not_internal,
    assert_hostname_resolves_to_public_ips,
    validate_https_service_endpoint_url,
)

__all__ = [
    "PipefyTomlConfigSource",
    "__version__",
    "assert_hostname_is_not_internal",
    "assert_hostname_resolves_to_public_ips",
    "config_dir",
    "config_file_path",
    "validate_https_service_endpoint_url",
]
