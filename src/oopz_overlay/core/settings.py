from __future__ import annotations

import json
import os
import math
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AppSettings:
    schema_version: int = 10
    device_id: str = field(default="", metadata={"persist": False})
    person_uid: str = field(default="", metadata={"persist": False})
    jwt_token: str = field(default="", metadata={"persist": False})
    app_version: str = field(default="69514", metadata={"persist": False})
    area_id: str = ""
    area_name: str = ""
    channel_id: str = ""
    channel_name: str = ""
    screen_name: str = ""
    hotkey: str = "F8"
    visibility_hotkey: str = "F9"
    position_x: float = 0.16
    position_y: float = 0.82
    overlay_width: int = 0
    overlay_height: int = 0
    always_visible: bool = True
    font_size: int = 12
    text_opacity: int = 100
    backdrop_opacity: int = 15
    notification_sound: str = "Windows Navigation Start.wav"

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> AppSettings:
        known = {
            item.name for item in fields(cls) if item.metadata.get("persist", True)
        }
        data = {key: value for key, value in raw.items() if key in known}
        for key in (
            "area_id",
            "area_name",
            "channel_id",
            "channel_name",
            "screen_name",
            "hotkey",
            "visibility_hotkey",
            "notification_sound",
        ):
            if key in data and not isinstance(data[key], str):
                raise ValueError(f"invalid setting: {key}")
        data["schema_version"] = 10
        data.setdefault("notification_sound", "")
        if "always_visible" in data and not isinstance(data["always_visible"], bool):
            raise ValueError("invalid setting: always_visible")
        # Fold 1.0's coupled slider into the effective values exactly once.
        delta = 0
        if raw.get("schema_version") == 9:
            delta = max(0, min(100, int(raw.get("strength", 50)))) - 50
        if "position_x" not in data:
            data["position_x"] = 0.5
        if "position_y" not in data:
            data["position_y"] = 0.82
        data["font_size"] = max(9, min(20, int(data.get("font_size", 12))))
        data["text_opacity"] = max(
            20,
            min(100, int(data.get("text_opacity", 100)) + round(delta * .8)),
        )
        data["backdrop_opacity"] = max(
            0,
            min(85, int(data.get("backdrop_opacity", 32)) + delta),
        )
        for key, fallback in (("position_x", 0.5), ("position_y", 0.82)):
            value = float(data.get(key, fallback))
            data[key] = max(0.0, min(1.0, value)) if math.isfinite(value) else fallback
        for key in ("overlay_width", "overlay_height"):
            data[key] = max(0, min(16000, int(data.get(key, 0))))
        return cls(**data)

    @property
    def opacity(self) -> tuple[int, int]:
        return self.backdrop_opacity, self.text_opacity

    @property
    def has_credentials(self) -> bool:
        return all((self.device_id, self.person_uid, self.jwt_token))

    @property
    def is_ready(self) -> bool:
        return self.has_credentials and bool(self.area_id and self.channel_id)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        for item in fields(self):
            if not item.metadata.get("persist", True):
                payload.pop(item.name, None)
        return payload


class SecretProtector(Protocol):
    def protect(self, plaintext: bytes) -> bytes: ...

    def unprotect(self, ciphertext: bytes) -> bytes: ...


class JsonSettingsStore:
    def __init__(self, path: Path, protector: SecretProtector) -> None:
        self.path = path
        self.protector = protector

    def load(self) -> AppSettings:
        if not self.path.is_file():
            return AppSettings()
        protected = self.path.read_bytes()
        payload = self.protector.unprotect(protected)
        raw = json.loads(payload.decode("utf-8"))
        if not isinstance(raw, dict):
            raise TypeError("settings payload must be an object")
        return AppSettings.from_dict(raw)

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            settings.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        protected = self.protector.protect(payload)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_bytes(protected)
        os.replace(temporary, self.path)
