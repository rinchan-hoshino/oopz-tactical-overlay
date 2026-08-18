import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from oopz_overlay.main import AppController, _close_onefile_splash


def test_app_controller_constructs_with_owned_state_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])

    controller = AppController(app)

    app.processEvents()
    assert controller.state_root == tmp_path / "RinChan" / "OopzTacticalOverlay"
    assert controller.tray.isVisible()
    assert controller._update_status == "更新 // 等待自动检查"

    controller.overlay.set_connection_status("#塔科夫", True)
    controller.overlay.show_overlay()
    assert controller.overlay.is_active

    controller.open_settings()
    app.processEvents()
    assert not controller.overlay.is_active
    assert controller.setup_dialog is not None
    assert controller.setup_dialog.isVisible()
    monkeypatch.setattr(controller.monitor, "hotkey_pressed", lambda hotkey: True)
    controller._poll_hotkey()
    app.processEvents()
    assert controller.overlay.is_active
    assert not controller.setup_dialog.isVisible()

    controller.overlay.hide_overlay()
    controller.setup_dialog.close()
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
