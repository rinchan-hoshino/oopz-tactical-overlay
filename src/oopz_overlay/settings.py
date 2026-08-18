from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Protocol

DEFAULT_FONT_SIZE = 12


class Protector(Protocol):
    def protect(self, plaintext: bytes) -> bytes: ...

    def unprotect(self, ciphertext: bytes) -> bytes: ...


@dataclass(frozen=True, slots=True)
class AppSettings:
    schema_version: int = 4
    device_id: str = ""
    person_uid: str = ""
    jwt_token: str = ""
    app_version: str = ""
    area_id: str = ""
    area_name: str = ""
    channel_id: str = ""
    channel_name: str = ""
    hotkey: str = "F8"
    position_x: float = 0.5
    position_y: float = 0.82
    overlay_width: int = 0
    overlay_height: int = 0
    always_visible: bool = True
    font_size: int = DEFAULT_FONT_SIZE

    @property
    def has_credentials(self) -> bool:
        return all((self.device_id, self.person_uid, self.jwt_token))

    @property
    def is_ready(self) -> bool:
        return self.has_credentials and bool(self.area_id and self.channel_id)


class JsonSettingsStore:
    def __init__(self, path: Path, protector: Protector) -> None:
        self.path = path
        self.protector = protector

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        plaintext = self.protector.unprotect(self.path.read_bytes())
        payload = json.loads(plaintext.decode("utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("settings payload must be an object")
        allowed = {
            item.name
            for item in fields(AppSettings)
            if item.metadata.get("persist", True)
        }
        migrated = {key: value for key, value in payload.items() if key in allowed}
        version = int(payload.get("schema_version", 0))
        if version < 2:
            migrated.update(
                position_x=0.5,
                position_y=0.82,
                always_visible=True,
            )
        migrated["schema_version"] = 4
        migrated["font_size"] = max(
            9,
            min(20, int(payload.get("font_size", DEFAULT_FONT_SIZE))),
        )
        return AppSettings(**migrated)

    def save(self, settings: AppSettings) -> None:
        payload = asdict(settings)
        for item in fields(AppSettings):
            if not item.metadata.get("persist", True):
                payload.pop(item.name, None)
        plaintext = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        ciphertext = self.protector.protect(plaintext)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_bytes(ciphertext)
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(self.path)
