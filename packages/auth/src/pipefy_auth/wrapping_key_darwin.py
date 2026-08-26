"""Create-once wrapping key in the macOS Keychain, allow-all ACL.

NULL trusted-application list on ``SecAccessCreate`` means any process of this
user can read the item without an ACL prompt. The session blob never lives
here — only a 32-byte AES key that is not rewritten on refresh.
"""

from __future__ import annotations

import ctypes
import functools
import os
from ctypes import byref, c_int32, c_uint32, c_void_p
from ctypes.util import find_library

from pipefy_auth.keychain_choice import (
    WRAPPING_KEY_BYTES,
    WRAPPING_KEYCHAIN_ACCOUNT,
    WRAPPING_KEYCHAIN_SERVICE,
)
from pipefy_auth.wrapping_key import require_persisted_wrapping_key

_ERR_SUCCESS = 0
_ERR_ITEM_NOT_FOUND = -25300
_ERR_DUPLICATE_ITEM = -25299

_OSStatus = c_int32


def _load_framework(name: str) -> ctypes.CDLL:
    path = find_library(name)
    if path is None:
        raise OSError(f"framework {name!r} is not available on this process")
    return ctypes.CDLL(path)


_sec = _load_framework("Security")
_found = _load_framework("Foundation")

CFDictionaryCreate = _found.CFDictionaryCreate
CFDictionaryCreate.restype = c_void_p
CFDictionaryCreate.argtypes = (
    c_void_p,
    c_void_p,
    c_void_p,
    c_int32,
    c_void_p,
    c_void_p,
)

CFStringCreateWithCString = _found.CFStringCreateWithCString
CFStringCreateWithCString.restype = c_void_p
CFStringCreateWithCString.argtypes = [c_void_p, c_void_p, c_uint32]

CFNumberCreate = _found.CFNumberCreate
CFNumberCreate.restype = c_void_p
CFNumberCreate.argtypes = [c_void_p, c_uint32, c_void_p]

CFDataCreate = _found.CFDataCreate
CFDataCreate.restype = c_void_p
CFDataCreate.argtypes = [c_void_p, c_void_p, ctypes.c_long]

SecItemAdd = _sec.SecItemAdd
SecItemAdd.restype = _OSStatus
SecItemAdd.argtypes = (c_void_p, c_void_p)

SecItemCopyMatching = _sec.SecItemCopyMatching
SecItemCopyMatching.restype = _OSStatus
SecItemCopyMatching.argtypes = (c_void_p, c_void_p)

SecAccessCreate = _sec.SecAccessCreate
SecAccessCreate.restype = _OSStatus
SecAccessCreate.argtypes = (c_void_p, c_void_p, c_void_p)

CFDataGetBytePtr = _found.CFDataGetBytePtr
CFDataGetBytePtr.restype = c_void_p
CFDataGetBytePtr.argtypes = (c_void_p,)

CFDataGetLength = _found.CFDataGetLength
CFDataGetLength.restype = c_int32
CFDataGetLength.argtypes = (c_void_p,)


def _k(symbol: str) -> c_void_p:
    return c_void_p.in_dll(_sec, symbol)


@functools.singledispatch
def _cf(value: object) -> object:
    return value


@_cf.register(bool)
@_cf.register(int)
def _(val: bool | int) -> c_void_p:
    k_int32 = 0x9
    return CFNumberCreate(None, k_int32, ctypes.byref(c_int32(int(val))))


@_cf.register
def _(text: str) -> c_void_p:
    utf8 = 0x08000100
    return CFStringCreateWithCString(None, text.encode("utf-8"), utf8)


@_cf.register
def _(raw: bytes) -> c_void_p:
    return CFDataCreate(None, raw, len(raw))


def _query(**kwargs: object) -> c_void_p:
    keys = (c_void_p * len(kwargs))(*map(_k, kwargs.keys()))
    values = (c_void_p * len(kwargs))(*map(_cf, kwargs.values()))
    return CFDictionaryCreate(
        None,
        keys,
        values,
        len(kwargs),
        _found.kCFTypeDictionaryKeyCallBacks,
        _found.kCFTypeDictionaryValueCallBacks,
    )


def _raise_osstatus(status: int, action: str) -> None:
    if status == _ERR_SUCCESS:
        return
    raise OSError(
        f"{action} failed with OSStatus {status} for Keychain service "
        f"{WRAPPING_KEYCHAIN_SERVICE!r} account {WRAPPING_KEYCHAIN_ACCOUNT!r}"
    )


def _copy_wrapping_key() -> bytes | None:
    query = _query(
        kSecClass=_k("kSecClassGenericPassword"),
        kSecMatchLimit=_k("kSecMatchLimitOne"),
        kSecAttrService=WRAPPING_KEYCHAIN_SERVICE,
        kSecAttrAccount=WRAPPING_KEYCHAIN_ACCOUNT,
        kSecReturnData=True,
    )
    data = c_void_p()
    status = int(SecItemCopyMatching(query, byref(data)))
    if status == _ERR_ITEM_NOT_FOUND:
        return None
    _raise_osstatus(status, "SecItemCopyMatching")
    return ctypes.string_at(CFDataGetBytePtr(data), CFDataGetLength(data))


def _allow_all_access() -> c_void_p:
    access = c_void_p()
    status = int(SecAccessCreate(_cf("pipefy wrapping key"), None, byref(access)))
    _raise_osstatus(status, "SecAccessCreate")
    return access


def _add_wrapping_key(key: bytes) -> None:
    query = _query(
        kSecClass=_k("kSecClassGenericPassword"),
        kSecAttrService=WRAPPING_KEYCHAIN_SERVICE,
        kSecAttrAccount=WRAPPING_KEYCHAIN_ACCOUNT,
        kSecValueData=key,
        kSecAttrAccess=_allow_all_access(),
    )
    status = int(SecItemAdd(query, None))
    if status == _ERR_DUPLICATE_ITEM:
        return
    _raise_osstatus(status, "SecItemAdd")


class DarwinKeychainWrappingKey:
    """32-byte AES key, created once in the login keychain."""

    def __init__(self) -> None:
        self._cached: bytes | None = None

    def load(self) -> bytes | None:
        if self._cached is not None:
            return self._cached
        existing = _copy_wrapping_key()
        if existing is None:
            return None
        if len(existing) != WRAPPING_KEY_BYTES:
            raise OSError(
                f"Keychain wrapping key for service {WRAPPING_KEYCHAIN_SERVICE!r} "
                f"has {len(existing)} bytes, expected {WRAPPING_KEY_BYTES}"
            )
        self._cached = existing
        return existing

    def load_or_create(self) -> bytes:
        existing = self.load()
        if existing is not None:
            return existing
        _add_wrapping_key(os.urandom(WRAPPING_KEY_BYTES))
        self._cached = require_persisted_wrapping_key(
            _copy_wrapping_key(),
            location=(
                f"Keychain service {WRAPPING_KEYCHAIN_SERVICE!r} "
                f"account {WRAPPING_KEYCHAIN_ACCOUNT!r}"
            ),
        )
        return self._cached
