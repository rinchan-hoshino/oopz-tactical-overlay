from __future__ import annotations

import base64
import json

import pytest

from oopz_overlay.local_session import LocalSessionError, parse_oopz_login_value


def _jwt(exp: int) -> str:
    def encode(value: object) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{encode({'alg': 'none'})}.{encode({'exp': exp})}.signature"


def _registry_value(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.b64encode(raw).decode()


def test_reads_credentials_from_existing_oopz_login_state() -> None:
    value = _registry_value(
        {
            "uid": "person-uid",
            "signature": _jwt(2_000_000_000),
            "deviceId": "device-id",
            "autoLogin": True,
        }
    )

    settings = parse_oopz_login_value(value, now=1_900_000_000)

    assert settings.person_uid == "person-uid"
    assert settings.device_id == "device-id"
    assert settings.jwt_token.count(".") == 2


def test_rejects_expired_local_session() -> None:
    value = _registry_value(
        {
            "uid": "person-uid",
            "signature": _jwt(1_800_000_000),
            "deviceId": "device-id",
        }
    )

    with pytest.raises(LocalSessionError, match="打开 Oopz"):
        parse_oopz_login_value(value, now=1_900_000_000)


def test_rejects_incomplete_or_malformed_state() -> None:
    with pytest.raises(LocalSessionError):
        parse_oopz_login_value("not-base64", now=1_900_000_000)

    value = _registry_value({"uid": "person-uid"})
    with pytest.raises(LocalSessionError):
        parse_oopz_login_value(value, now=1_900_000_000)
