from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AppSettings:
    schema_version: int = 7
    hotkey: str = "F8"
    visibility_hotkey: str = "F9"
    position_x: float = 0.5
    position_y: float = 0.82
    overlay_width: int = 0
    overlay_height: int = 0
    always_visible: bool = True
    font_size: int = 12
    text_opacity: int = 100
    backdrop_opacity: int = 32

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> AppSettings:
        known = {item.name for item in fields(cls)}
        data = {key: value for key, value in raw.items() if key in known}
        data["schema_version"] = 7
        if "position_x" not in data:
            data["position_x"] = 0.5
        if "position_y" not in data:
            data["position_y"] = 0.82
        if "always_visible" not in data or "position_x" not in raw:
            data["always_visible"] = True
        data["font_size"] = max(9, min(20, int(data.get("font_size", 12))))
        data["text_opacity"] = max(
            20,
            min(100, int(data.get("text_opacity", 100))),
        )
        data["backdrop_opacity"] = max(
            0,
            min(85, int(data.get("backdrop_opacity", 32))),
        )
        return cls(**data)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


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
