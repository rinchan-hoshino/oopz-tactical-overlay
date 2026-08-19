import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from oopz_overlay.chat import ChatMessage
from oopz_overlay.main import AppController, _close_onefile_splash
from oopz_overlay.settings import AppSettings


def test_app_controller_constructs_with_owned_state_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])

    controller = AppController(app)

    app.processEvents()
    assert controller.state_root == tmp_path / "RinChan" / "OopzTacticalOverlay"
    assert controller.tray.isVisible()
    assert controller._update_status == "等待检查更新"

    controller.overlay.set_connection_status("#塔科夫", True)
    controller.overlay.show_overlay()
    assert controller.overlay.is_active

    controller.open_settings()
    app.processEvents()
    assert not controller.overlay.is_active
    assert controller.setup_dialog is not None
    assert controller.setup_dialog.isVisible()
    controller._activate_overlay()
    app.processEvents()
    assert controller.overlay.is_active
    assert not controller.setup_dialog.isVisible()

    controller.overlay.hide_overlay()
    controller.setup_dialog.close()
    controller.shutdown()
    app.processEvents()


def test_manual_channel_change_clears_timeline_and_reconnects(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    controller = AppController(app)
    connected: list[AppSettings] = []
    monkeypatch.setattr(controller.gateway, "connect", connected.append)
    monkeypatch.setattr(controller.hotkeys, "configure", lambda *_args: None)
    controller.overlay.merge_messages(
        [ChatMessage("old", 1, "u", "风屿", "旧频道消息", False)]
    )
    settings = AppSettings(
        device_id="device",
        person_uid="person",
        jwt_token="token",
        area_id="area",
        area_name="猫尾服务器",
        channel_id="strategy",
        channel_name="攻略",
    )

    controller._configured(settings)

    assert controller.overlay.timeline.items == ()
    assert connected == [settings]
    controller.shutdown()
    app.processEvents()


def test_visibility_hotkey_toggles_the_passive_hud(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    controller = AppController(app)
    controller.settings = AppSettings(hotkey="F8", visibility_hotkey="F9")
    controller.overlay.configure(controller.settings)
    controller.overlay.set_connection_status("#塔科夫", True)
    controller._toggle_visibility()
    app.processEvents()

    assert controller.overlay.isHidden()
    controller.shutdown()
    app.processEvents()


def test_onefile_splash_feedback_is_removed_when_ui_is_ready(
    tmp_path, monkeypatch
) -> None:
    feedback = tmp_path / "onefile_4321_splash_feedback.tmp"
    feedback.write_text("")
    monkeypatch.setenv("NUITKA_ONEFILE_PARENT", "4321")
    monkeypatch.setattr("oopz_overlay.main.gettempdir", lambda: str(tmp_path))

    _close_onefile_splash()

    assert not feedback.exists()
