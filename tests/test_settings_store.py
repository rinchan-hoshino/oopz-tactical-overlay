import json

from oopz_overlay.settings import AppSettings, JsonSettingsStore


class ReversingProtector:
    def protect(self, plaintext: bytes) -> bytes:
        return plaintext[::-1]

    def unprotect(self, ciphertext: bytes) -> bytes:
        return ciphertext[::-1]


def test_secret_fields_are_not_written_as_plaintext(tmp_path) -> None:
    path = tmp_path / "state.bin"
    store = JsonSettingsStore(path, ReversingProtector())
    settings = AppSettings(
        device_id="device",
        person_uid="person",
        jwt_token="very-secret-token",
        area_id="area",
        area_name="猫尾草",
        channel_id="channel",
        channel_name="塔科夫",
        hotkey="Ctrl+Enter",
        position_x=0.74,
        position_y=0.66,
        always_visible=False,
        font_size=18,
    )

    store.save(settings)

    raw = path.read_bytes()
    assert b"very-secret-token" not in raw
    plaintext = json.loads(raw[::-1])
    assert "target_process" not in plaintext
    assert "target_process_id" not in plaintext
    assert store.load() == settings


def test_legacy_settings_ignore_removed_process_and_numeric_position(tmp_path) -> None:
    path = tmp_path / "state.bin"
    legacy = {
        "target_process": "EscapeFromTarkov.exe",
        "anchor": "bottom-right",
        "offset_x": -24,
        "offset_y": 18,
        "always_visible": False,
        "hotkey": "F8",
    }
    path.write_bytes(json.dumps(legacy).encode()[::-1])

    loaded = JsonSettingsStore(path, ReversingProtector()).load()

    assert loaded.schema_version == 4
    assert not hasattr(loaded, "target_process")
    assert loaded.hotkey == "F8"
    assert loaded.position_x == 0.5
    assert loaded.position_y == 0.82
    assert loaded.always_visible is True


def test_existing_hotkey_is_preserved_while_new_default_is_f8(tmp_path) -> None:
    path = tmp_path / "state.bin"
    path.write_bytes(
        json.dumps({"schema_version": 2, "hotkey": "Enter"}).encode()[::-1]
    )

    loaded = JsonSettingsStore(path, ReversingProtector()).load()

    assert loaded.schema_version == 4
    assert loaded.hotkey == "Enter"
    assert loaded.font_size == 12
    assert AppSettings().hotkey == "F8"


def test_missing_settings_returns_defaults(tmp_path) -> None:
    store = JsonSettingsStore(tmp_path / "missing.bin", ReversingProtector())

    assert store.load() == AppSettings()
