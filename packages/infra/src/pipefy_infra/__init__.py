"""Schema-agnostic infrastructure helpers shared by ``pipefy_sdk`` and ``pipefy_auth``.

The package root exposes only ``__version__``. Consumers import from the
submodule that names the concern: :mod:`pipefy_infra.config` (on-disk
configuration: path discovery + TOML source), :mod:`pipefy_infra.security`
(SSRF defenses, imported as ``from pipefy_infra import security`` so every
call site is greppable for audits), and :mod:`pipefy_infra.coerce`
(permissive type-coercion helpers for JSON/GraphQL response values). See
each submodule docstring and ``README.md`` for the detailed surface. The
package sits at the bottom of the workspace dependency graph: stdlib +
``pydantic`` / ``pydantic-settings`` only.
"""

from __future__ import annotations

__version__ = "0.2.0-beta.4"

__all__ = ["__version__"]
