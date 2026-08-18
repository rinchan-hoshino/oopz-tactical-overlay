from __future__ import annotations

import base64
import json
import os
import time
from collections.abc import Callable

from .settings import AppSettings


class LocalSessionError(RuntimeError):
    pass


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


def parse_oopz_login_value(value: str, *, now: float | None = None) -> AppSettings:
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

    return AppSettings(
        device_id=device_id,
        person_uid=person_uid,
        jwt_token=token,
    )


def load_oopz_local_session(
    reader: Callable[[], str] | None = None,
) -> AppSettings:
    if reader is None:
        if os.name != "nt":
            raise LocalSessionError("只能在安装了 Oopz 的 Windows 用户中读取登录态。")
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
