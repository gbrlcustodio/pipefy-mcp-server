"""Guard: the auth public API takes refined value objects, never a config instance.

Encodes the parse-don't-validate rule from ``AGENTS.md`` as an executable check:
the public ``__init__`` exports no ``*Config`` / ``*Settings`` symbol, and the
public entry points (``JwtValidator``, ``resolve_pipefy_auth``,
``detect_pipefy_tiers``) annotate no parameter with such a type. A regression
(re-exporting a reader, or widening a signature back to a config instance) fails
here rather than in review.
"""

from __future__ import annotations

import inspect

import pytest

import pipefy_auth
from pipefy_auth import JwtValidator, detect_pipefy_tiers, resolve_pipefy_auth

_BANNED_SUFFIXES = ("Config", "Settings")


@pytest.mark.unit
def test_public_api_exports_no_config_or_settings_symbol():
    offenders = [
        name for name in pipefy_auth.__all__ if name.endswith(_BANNED_SUFFIXES)
    ]
    assert offenders == [], (
        "pipefy_auth public API must expose refined value objects, not config "
        f"instances; found: {offenders}"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "func",
    [JwtValidator.__init__, resolve_pipefy_auth, detect_pipefy_tiers],
    ids=lambda f: f.__qualname__,
)
def test_signatures_take_no_config_instance(func):
    for name, param in inspect.signature(func).parameters.items():
        annotation = str(param.annotation)
        assert not annotation.endswith(_BANNED_SUFFIXES), (
            f"{func.__qualname__} parameter {name!r} is annotated {annotation!r}; "
            "public APIs take refined value objects, never a *Config / *Settings."
        )
