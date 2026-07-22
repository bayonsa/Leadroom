from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes

PREFIX = "dpapi:"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def protect_secret(value: str) -> str:
    if not value or value.startswith(PREFIX) or os.name != "nt":
        return value
    raw = value.encode("utf-8")
    buffer = ctypes.create_string_buffer(raw)
    source = _DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    protected = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), "Leadroom secret", None, None, None, 0x1, ctypes.byref(protected)
    ):
        raise ctypes.WinError()
    try:
        payload = ctypes.string_at(protected.pbData, protected.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(protected.pbData)
    return PREFIX + base64.b64encode(payload).decode("ascii")


def reveal_secret(value: str) -> str:
    if not value.startswith(PREFIX):
        return value
    if os.name != "nt":
        raise RuntimeError("This protected secret can only be opened by its Windows user")
    raw = base64.b64decode(value[len(PREFIX) :], validate=True)
    buffer = ctypes.create_string_buffer(raw)
    source = _DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    clear = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(clear)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(clear.pbData, clear.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(clear.pbData)
