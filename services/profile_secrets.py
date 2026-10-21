"""Local Windows user-bound token storage. Tokens never enter the registry."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import tempfile
import re


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data: bytes, *, decrypt: bool = False) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Profile token storage requires Windows DPAPI.")
    buffer = ctypes.create_string_buffer(data)
    source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = _Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    protect = crypt32.CryptProtectData
    protect.argtypes = [ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    protect.restype = wintypes.BOOL
    unprotect = crypt32.CryptUnprotectData
    unprotect.argtypes = [ctypes.POINTER(_Blob), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    unprotect.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    function = unprotect if decrypt else protect
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise RuntimeError("Unable to access protected profile token.")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel32.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


def _validate_profile_id(profile_id: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", profile_id):
        raise ValueError("Invalid profile id for protected token storage.")


def save_token(profile_id: str, token: str, base_dir: Path) -> None:
    _validate_profile_id(profile_id)
    directory = Path(base_dir) / ".profile-secrets"
    directory.mkdir(parents=True, exist_ok=True)
    protected = _crypt(token.encode("utf-8"))
    fd, filename = tempfile.mkstemp(dir=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(protected)
        os.replace(filename, directory / (profile_id + ".bin"))
    finally:
        Path(filename).unlink(missing_ok=True)


def load_token(profile_id: str, base_dir: Path) -> str:
    _validate_profile_id(profile_id)
    path = Path(base_dir) / ".profile-secrets" / (profile_id + ".bin")
    if not path.is_file():
        return ""
    return _crypt(path.read_bytes(), decrypt=True).decode("utf-8")
