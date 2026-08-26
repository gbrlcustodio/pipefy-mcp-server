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

from pipefy_auth.keychain_choice import WRAPPING_KEY_BYTES

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


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


class WindowsDpapiWrappingKey:
    """32-byte AES key, DPAPI-encrypted beside the session file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._cached: bytes | None = None

    def load_or_create(self) -> bytes:
        if self._cached is not None:
            return self._cached
        if self._path.exists():
            key = dpapi_unprotect(self._path.read_bytes())
            if len(key) != WRAPPING_KEY_BYTES:
                raise OSError(
                    f"DPAPI wrapping key at {self._path} has {len(key)} bytes, "
                    f"expected {WRAPPING_KEY_BYTES}"
                )
            self._cached = key
            return key
        key = os.urandom(WRAPPING_KEY_BYTES)
        _atomic_write(self._path, dpapi_protect(key))
        self._cached = key
        return key
