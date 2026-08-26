"""Create-once wrapping key encrypted with Windows DPAPI.

The 32-byte AES key is ``CryptProtectData``'d into ``wrapping.key`` under the
Pipefy config directory. Refresh rewrites only ``session.enc``.
"""

from __future__ import annotations

import os
from ctypes import (
    POINTER,
    WINFUNCTYPE,
    Structure,
    WinDLL,
    byref,
    c_char_p,
    c_void_p,
    cast,
    create_string_buffer,
    memmove,
    windll,
    wintypes,
)
from pathlib import Path

from pipefy_auth.atomic_replace import replace_file_atomically
from pipefy_auth.keychain_choice import WRAPPING_KEY_BYTES
from pipefy_auth.wrapping_key import (
    create_once_file_wrapping_key,
    require_persisted_wrapping_key,
)

_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _DATA_BLOB(Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", POINTER(wintypes.BYTE))]


_crypt32 = WinDLL("CRYPT32.DLL")

_CryptProtectData = WINFUNCTYPE(
    wintypes.BOOL,
    POINTER(_DATA_BLOB),
    POINTER(wintypes.WCHAR),
    POINTER(_DATA_BLOB),
    c_void_p,
    c_void_p,
    wintypes.DWORD,
    POINTER(_DATA_BLOB),
)(("CryptProtectData", _crypt32))

_CryptUnprotectData = WINFUNCTYPE(
    wintypes.BOOL,
    POINTER(_DATA_BLOB),
    POINTER(wintypes.WCHAR),
    POINTER(_DATA_BLOB),
    c_void_p,
    c_void_p,
    wintypes.DWORD,
    POINTER(_DATA_BLOB),
)(("CryptUnprotectData", _crypt32))


def _blob(data: bytes) -> _DATA_BLOB:
    return _DATA_BLOB(
        cbData=len(data),
        pbData=cast(c_char_p(data), POINTER(wintypes.BYTE)),
    )


def _copy_out(blob: _DATA_BLOB) -> bytes:
    buf = create_string_buffer(blob.cbData)
    memmove(buf, blob.pbData, blob.cbData)
    windll.kernel32.LocalFree(blob.pbData)
    return buf.raw


def dpapi_protect(plaintext: bytes) -> bytes:
    incoming = _blob(plaintext)
    outgoing = _DATA_BLOB()
    if not _CryptProtectData(
        byref(incoming),
        "pipefy-wrapping-key",
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        byref(outgoing),
    ):
        raise OSError("CryptProtectData failed for the Pipefy wrapping key")
    return _copy_out(outgoing)


def dpapi_unprotect(ciphertext: bytes) -> bytes:
    incoming = _blob(ciphertext)
    outgoing = _DATA_BLOB()
    if not _CryptUnprotectData(
        byref(incoming),
        None,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        byref(outgoing),
    ):
        raise OSError("CryptUnprotectData failed for the Pipefy wrapping key")
    return _copy_out(outgoing)


class WindowsDpapiWrappingKey:
    """32-byte AES key, DPAPI-encrypted beside the session file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._cached: bytes | None = None

    def load(self) -> bytes | None:
        if self._cached is not None:
            return self._cached
        if not self._path.exists():
            return None
        self._cached = require_persisted_wrapping_key(
            dpapi_unprotect(self._path.read_bytes()),
            location=str(self._path),
        )
        return self._cached

    def load_or_create(self) -> bytes:
        self._cached = create_once_file_wrapping_key(
            cached=self._cached,
            path=self._path,
            read_unprotected=lambda: dpapi_unprotect(self._path.read_bytes()),
            write_protected=lambda minted: replace_file_atomically(
                self._path, dpapi_protect(minted)
            ),
            mint=lambda: os.urandom(WRAPPING_KEY_BYTES),
        )
        return self._cached
