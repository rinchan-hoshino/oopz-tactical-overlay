import json

from oopz_overlay.settings import AppSettings, JsonSettingsStore


class ReversingProtector:
    def protect(self, plaintext: bytes) -> bytes:
        return plaintext[::-1]

    def unprotect(self, ciphertext: bytes) -> bytes:
        return ciphertext[::-1]


def test_settings_store_contains_no_oopz_credentials(tmp_path) -> None:
    path = tmp_path / "state.bin"
    store = JsonSettingsStore(path, ReversingProtector())
    settings = AppSettings(
        device_id="device",
        person_uid="person",
        jwt_token="token",
        area_id="area",
        area_name="猫尾服务器",
        channel_id="channel",
        channel_name="综合文字",
        hotkey="Ctrl+Enter",
        position_x=0.74,
        position_y=0.66,
        always_visible=False,
        font_size=18,
        visibility_hotkey="Ctrl+F9",
        text_opacity=72,
        backdrop_opacity=38,
    )

    store.save(settings)

    raw = path.read_bytes()
    plaintext = json.loads(raw[::-1])
    assert "device_id" not in plaintext
    assert "person_uid" not in plaintext
    assert "jwt_token" not in plaintext
    assert "target_process" not in plaintext
    assert "target_process_id" not in plaintext
    assert plaintext["area_id"] == "area"
    assert plaintext["channel_id"] == "channel"
    loaded = store.load()
    assert loaded.area_id == "area"
    assert loaded.channel_id == "channel"
    assert not loaded.has_credentials


def test_legacy_settings_ignore_removed_process_and_numeric_position(tmp_path) -> None:
    path = tmp_path / "state.bin"
    legacy = {
        "target_process": "EscapeFromTarkov.exe",
        "anchor": "bottom-right",
        "offset_x": -24,
        "offset_y": 18,
        "always_visible": False,
        "hotkey": "F8",
        "device_id": "removed",
        "person_uid": "removed",
        "jwt_token": "removed",
        "area_id": "removed",
        "channel_id": "removed",
    }
    path.write_bytes(json.dumps(legacy).encode()[::-1])

    loaded = JsonSettingsStore(path, ReversingProtector()).load()

    assert loaded.schema_version == 8
    assert not hasattr(loaded, "target_process")
    assert loaded.jwt_token == ""
    assert loaded.area_id == "removed"
    assert loaded.channel_id == "removed"
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

    assert loaded.schema_version == 8
    assert loaded.hotkey == "Enter"
    assert loaded.visibility_hotkey == "F9"
    assert loaded.font_size == 12
    assert loaded.text_opacity == 100
    assert loaded.backdrop_opacity == 32
    assert AppSettings().hotkey == "F8"


def test_visual_settings_are_clamped_when_loading(tmp_path) -> None:
    path = tmp_path / "state.bin"
    path.write_bytes(
        json.dumps(
            {
                "schema_version": 5,
                "font_size": 80,
                "text_opacity": -5,
                "backdrop_opacity": 140,
            }
        ).encode()[::-1]
    )

    loaded = JsonSettingsStore(path, ReversingProtector()).load()

    assert loaded.font_size == 20
    assert loaded.text_opacity == 20
    assert loaded.backdrop_opacity == 85


def test_missing_settings_returns_defaults(tmp_path) -> None:
    store = JsonSettingsStore(tmp_path / "missing.bin", ReversingProtector())

    assert store.load() == AppSettings()
