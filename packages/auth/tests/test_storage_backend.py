"""Coverage for ``configure_keychain_backend`` (env-driven keyring swap)
and the on-disk blob round-trip for ``StoredSession``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import keyring
import pytest
from conftest import InMemoryKeyring
from keyring.errors import KeyringError
from keyrings.alt.file import PlaintextKeyring
from pydantic import ValidationError

from pipefy_auth.responses import TokenResponse
from pipefy_auth.storage import (
    StoredSession,
    configure_keychain_backend,
    keychain_key,
    load_session,
    session_entry_presence,
    store_session,
)

_SERVICE = "pipefy"
_ISSUER = "https://example.test/realms/pipefy"
_CLIENT_ID = "cli"


@pytest.fixture
def _isolated_keyring() -> Iterator[None]:
    """Reset the module-level keyring after each test (don't leak into siblings)."""
    original = keyring.get_keyring()
    yield
    keyring.set_keyring(original)


@pytest.fixture
def config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``config_dir()`` at ``tmp_path`` so file-backend writes stay sandboxed."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


@pytest.mark.unit
def test_file_backend_swaps_to_plaintext_keyring(
    _isolated_keyring: None,
    config_home: Path,
) -> None:
    """``configure_keychain_backend('file')`` installs a ``PlaintextKeyring`` under ``config_dir()``."""
    configure_keychain_backend("file")

    backend = keyring.get_keyring()
    assert isinstance(backend, PlaintextKeyring)
    assert backend.file_path == str(config_home / "pipefy" / "keyring.cfg")


@pytest.mark.unit
def test_auto_backend_is_a_noop(
    _isolated_keyring: None,
) -> None:
    """``configure_keychain_backend('auto')`` leaves the active backend untouched."""
    before = keyring.get_keyring()
    configure_keychain_backend("auto")
    assert keyring.get_keyring() is before


@pytest.mark.unit
def test_file_backend_is_idempotent(
    _isolated_keyring: None,
    config_home: Path,
) -> None:
    """Calling ``configure_keychain_backend('file')`` twice converges on the same backend."""
    configure_keychain_backend("file")
    first = keyring.get_keyring()
    configure_keychain_backend("file")
    second = keyring.get_keyring()

    assert isinstance(first, PlaintextKeyring)
    assert isinstance(second, PlaintextKeyring)
    assert first.file_path == second.file_path


@pytest.mark.unit
def test_file_backend_round_trip_writes_under_config_dir(
    _isolated_keyring: None,
    config_home: Path,
) -> None:
    """Once swapped, ``set_password`` / ``get_password`` go through the file backend."""
    configure_keychain_backend("file")
    keyring.set_password("pipefy-test", "user", "secret-value")

    backing_file = config_home / "pipefy" / "keyring.cfg"
    assert backing_file.exists()
    assert keyring.get_password("pipefy-test", "user") == "secret-value"


# --------------------------------------------------------------------------- #
# StoredSession blob round-trip                                               #
# --------------------------------------------------------------------------- #


def _token(access: str = "AT", refresh: str = "RT") -> TokenResponse:
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        token_type="Bearer",
        expires_in=300,
        refresh_expires_in=3600,
        scope="openid email",
        id_token="ID",
    )


@pytest.mark.unit
def test_store_session_writes_flat_blob_and_round_trips(
    fake_keyring: InMemoryKeyring,
) -> None:
    """``store_session`` emits the flat shape; ``load_session`` reads it back."""
    stored = store_session(issuer=_ISSUER, client_id=_CLIENT_ID, token=_token())

    raw = fake_keyring.get_password(_SERVICE, keychain_key(_ISSUER, _CLIENT_ID))
    assert raw is not None
    blob = json.loads(raw)
    assert "token" not in blob
    assert blob["access_token"] == "AT"
    assert blob["refresh_token"] == "RT"
    assert blob["issuer"] == _ISSUER

    loaded = load_session(issuer=_ISSUER, client_id=_CLIENT_ID)
    assert loaded == stored


@pytest.mark.unit
def test_load_session_accepts_legacy_flat_blob(
    fake_keyring: InMemoryKeyring,
) -> None:
    """Pre-pydantic keychain entries (flat, no ``token`` key) still load."""
    legacy = {
        "issuer": _ISSUER,
        "client_id": _CLIENT_ID,
        "obtained_at": 1700000000,
        "access_token": "AT",
        "refresh_token": "RT",
        "token_type": "Bearer",
        "expires_in": 300,
        "refresh_expires_in": 3600,
        "scope": "openid email",
        "id_token": "ID",
    }
    fake_keyring.set_password(
        _SERVICE, keychain_key(_ISSUER, _CLIENT_ID), json.dumps(legacy)
    )

    loaded = load_session(issuer=_ISSUER, client_id=_CLIENT_ID)
    assert loaded is not None
    assert loaded.token.access_token == "AT"
    assert loaded.token.refresh_token == "RT"
    assert loaded.obtained_at == 1700000000


@pytest.mark.unit
def test_load_session_accepts_nested_blob(
    fake_keyring: InMemoryKeyring,
) -> None:
    """Forward-compat: explicit nested ``token`` also loads."""
    nested = {
        "issuer": _ISSUER,
        "client_id": _CLIENT_ID,
        "obtained_at": 1700000000,
        "token": {
            "access_token": "AT",
            "refresh_token": "RT",
            "token_type": "Bearer",
            "expires_in": 300,
            "refresh_expires_in": 3600,
            "scope": "openid email",
            "id_token": "ID",
        },
    }
    fake_keyring.set_password(
        _SERVICE, keychain_key(_ISSUER, _CLIENT_ID), json.dumps(nested)
    )

    loaded = load_session(issuer=_ISSUER, client_id=_CLIENT_ID)
    assert loaded is not None
    assert loaded.token.access_token == "AT"


@pytest.mark.unit
def test_load_session_returns_none_for_corrupt_json(
    fake_keyring: InMemoryKeyring,
) -> None:
    fake_keyring.set_password(_SERVICE, keychain_key(_ISSUER, _CLIENT_ID), "{not json")
    assert load_session(issuer=_ISSUER, client_id=_CLIENT_ID) is None


@pytest.mark.unit
def test_load_session_returns_none_when_required_field_missing(
    fake_keyring: InMemoryKeyring,
) -> None:
    """ValidationError on disk reads as 'no session' rather than crashing."""
    fake_keyring.set_password(
        _SERVICE,
        keychain_key(_ISSUER, _CLIENT_ID),
        json.dumps({"issuer": _ISSUER, "client_id": _CLIENT_ID, "obtained_at": 1}),
    )
    assert load_session(issuer=_ISSUER, client_id=_CLIENT_ID) is None


# --------------------------------------------------------------------------- #
# session_entry_presence                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_presence_is_absent_when_nothing_stored(
    fake_keyring: InMemoryKeyring,
) -> None:
    assert session_entry_presence(issuer=_ISSUER, client_id=_CLIENT_ID) == "absent"


@pytest.mark.unit
def test_presence_is_present_for_a_readable_entry(
    fake_keyring: InMemoryKeyring,
) -> None:
    store_session(issuer=_ISSUER, client_id=_CLIENT_ID, token=_token())
    assert session_entry_presence(issuer=_ISSUER, client_id=_CLIENT_ID) == "present"


@pytest.mark.unit
@pytest.mark.parametrize(
    "blob",
    [
        pytest.param("{not json", id="corrupt-json"),
        pytest.param(
            json.dumps({"issuer": _ISSUER, "client_id": _CLIENT_ID, "obtained_at": 1}),
            id="schema-drift",
        ),
        pytest.param("", id="empty-string"),
    ],
)
@pytest.mark.usefixtures("fake_keyring")
def test_presence_is_present_for_an_unparseable_entry(blob: str) -> None:
    """The whole point: an entry ``load_session`` cannot parse still exists."""
    keyring.set_password(_SERVICE, keychain_key(_ISSUER, _CLIENT_ID), blob)

    assert load_session(issuer=_ISSUER, client_id=_CLIENT_ID) is None
    assert session_entry_presence(issuer=_ISSUER, client_id=_CLIENT_ID) == "present"


@pytest.mark.unit
def test_presence_is_unknown_when_the_backend_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A backend that refuses the read leaves presence unestablished."""

    def _boom(service: str, username: str) -> str | None:
        raise KeyringError("keychain is locked")

    monkeypatch.setattr(keyring, "get_password", _boom)

    assert session_entry_presence(issuer=_ISSUER, client_id=_CLIENT_ID) == "unknown"


@pytest.mark.unit
def test_stored_session_rejects_bool_obtained_at() -> None:
    """``StrictInt`` rejects bool to prevent ``True`` masquerading as ``1``."""
    with pytest.raises(ValidationError):
        StoredSession(
            issuer=_ISSUER,
            client_id=_CLIENT_ID,
            obtained_at=True,  # type: ignore[arg-type]
            token=_token(),
        )


@pytest.mark.unit
def test_stored_session_forbids_unknown_outer_fields() -> None:
    """Unknown outer fields signal a corruption/hand-edit, not an IdP extension."""
    with pytest.raises(ValidationError):
        StoredSession.model_validate(
            {
                "issuer": _ISSUER,
                "client_id": _CLIENT_ID,
                "obtained_at": 1,
                "token": {"access_token": "a", "refresh_token": "r"},
                "unexpected": "x",
            }
        )
