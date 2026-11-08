from __future__ import annotations

import base64
import json
import os
import time
import ctypes
from ctypes import wintypes
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LocalOopzSession:
    device_id: str
    person_uid: str
    jwt_token: str
    app_version: str = "69514"


class LocalSessionError(RuntimeError):
    pass


class ProcessEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def _oopz_is_running() -> bool:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    for name in ("Process32FirstW", "Process32NextW"):
        getattr(kernel, name).argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        getattr(kernel, name).restype = wintypes.BOOL
    snapshot = kernel.CreateToolhelp32Snapshot(0x2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise LocalSessionError("无法检查 Oopz 是否运行，请稍后重试。")
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        found = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            if entry.szExeFile.casefold() == "oopz.exe":
                return True
            found = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        return False
    finally:
        kernel.CloseHandle(snapshot)


def _decode_jwt_exp(token: str) -> int | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode())
        value = json.loads(decoded)
        return int(value["exp"]) if "exp" in value else None
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def parse_oopz_login_value(
    value: str,
    *,
    now: float | None = None,
) -> LocalOopzSession:
    try:
        decoded = base64.b64decode(value, validate=True)
        payload = json.loads(decoded)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise LocalSessionError(
            "本机 Oopz 登录态无法识别，请先更新并重新登录 Oopz。"
        ) from exc
    if not isinstance(payload, dict):
        raise LocalSessionError("本机 Oopz 登录态格式不完整。")

    person_uid = str(payload.get("uid") or "").strip()
    token = str(payload.get("signature") or "").strip()
    device_id = str(payload.get("deviceId") or "").strip()
    if not person_uid or not token or not device_id:
        raise LocalSessionError("没有找到完整的 Oopz 登录态，请先打开并登录 Oopz。")

    expires_at = _decode_jwt_exp(token)
    if (
        expires_at is not None
        and expires_at <= int(now if now is not None else time.time()) + 60
    ):
        raise LocalSessionError("Oopz 登录态已经过期，请先打开 Oopz 完成登录或刷新。")

    return LocalOopzSession(
        device_id=device_id,
        person_uid=person_uid,
        jwt_token=token,
        app_version=str(payload.get("appVersion") or "69514"),
    )


def load_oopz_local_session(
    reader: Callable[[], str] | None = None,
) -> LocalOopzSession:
    if reader is None:
        if os.name != "nt":
            raise LocalSessionError("只能在安装了 Oopz 的 Windows 用户中读取登录态。")
        if not _oopz_is_running():
            raise LocalSessionError("Oopz 尚未运行，请先打开并登录 Oopz。")
        import winreg

        def reader() -> str:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Oopz\OopzData",
                ) as key:
                    value, _ = winreg.QueryValueEx(key, "login")
            except OSError as exc:
                raise LocalSessionError(
                    "没有找到已登录的 Oopz，请先打开并登录 Oopz。"
                ) from exc
            return str(value)

    return parse_oopz_login_value(reader())



import ctypes
import os
from ctypes import wintypes


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    return (
        _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))),
        buffer,
    )


class WindowsDpapiProtector:
    """Encrypt application state for the current Windows user with DPAPI."""

    def __init__(self, description: str = "Oopz Tactical Overlay") -> None:
        if os.name != "nt":
            raise OSError("Windows DPAPI is only available on Windows")
        self.description = description
        self._crypt32 = ctypes.windll.crypt32
        self._kernel32 = ctypes.windll.kernel32

    def protect(self, plaintext: bytes) -> bytes:
        source, keepalive = _blob(plaintext)
        output = _DataBlob()
        if not self._crypt32.CryptProtectData(
            ctypes.byref(source),
            self.description,
            None,
            None,
            None,
            0,
            ctypes.byref(output),
        ):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(output.pbData, output.cbData)
        finally:
            self._kernel32.LocalFree(output.pbData)
            del keepalive

    def unprotect(self, ciphertext: bytes) -> bytes:
        source, keepalive = _blob(ciphertext)
        output = _DataBlob()
        if not self._crypt32.CryptUnprotectData(
            ctypes.byref(source),
            None,
            None,
            None,
            None,
            0,
            ctypes.byref(output),
        ):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(output.pbData, output.cbData)
        finally:
            self._kernel32.LocalFree(output.pbData)
            del keepalive
