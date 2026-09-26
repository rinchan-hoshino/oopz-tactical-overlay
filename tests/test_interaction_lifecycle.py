import os

import pytest
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from oopz_overlay.instance import SingleInstance
from oopz_overlay.settings_dialog import SetupDialog
from oopz_overlay.settings import AppSettings
from oopz_overlay.widgets import OverlayWindow
from oopz_overlay.win32_input import (
    GlobalHotkeyRegistration,
    GlobalWheelRegistration,
    HOTKEY_ACTIVATE_ID,
    HOTKEY_VISIBILITY_ID,
    _restore_window_native,
)


def test_second_launch_opens_first_instance_and_releases_lock_on_exit(tmp_path):
    app = QApplication.instance() or QApplication([])
    first = SingleInstance(tmp_path)
    second = SingleInstance(tmp_path)
    successor = SingleInstance(tmp_path)
    activations = []
    first.activated.connect(lambda: activations.append(True))
    try:
        assert first.acquire()
        assert not second.acquire()
        QTest.qWait(30)
        assert activations == [True]
        first.close()
        assert successor.acquire()
    finally:
        first.close()
        second.close()
        successor.close()
        app.processEvents()


def test_ime_enter_does_not_send_uncommitted_text(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("oopz_overlay.widgets.focus_window", lambda *_: True)
    monkeypatch.setattr("oopz_overlay.widgets.prepare_input_method", lambda *_: True)
    overlay = OverlayWindow()
    received = []
    overlay.send_requested.connect(received.append)
    overlay.set_connection_status("ready", True)
    overlay.show_overlay()
    app.processEvents()
    overlay.input.setText("收到 ")
    QApplication.sendEvent(overlay.input, QInputMethodEvent("ni", []))
    QTest.keyClick(overlay.input, Qt.Key.Key_Return)
    assert received == []
    assert overlay.is_active
    committed = QInputMethodEvent()
    committed.setCommitString("你")
    QApplication.sendEvent(overlay.input, committed)
    QTest.keyClick(overlay.input, Qt.Key.Key_Return)
    assert received == ["收到 你"]
    assert not overlay.is_active
    overlay.hide()
    overlay.deleteLater()


def test_hotkey_conflict_restores_previous_keys_and_recording_releases_them():
    class User32:
        def __init__(self):
            self.keys = {}

        def RegisterHotKey(self, window, identifier, modifiers, key):
            if key == 0x79:  # F10 belongs to another application.
                return 0
            self.keys[identifier] = key
            return 1

        def UnregisterHotKey(self, window, identifier):
            self.keys.pop(identifier, None)
            return 1

    api = User32()
    registration = GlobalHotkeyRegistration(1, user32=api)
    registration.configure("F8", "F9")
    expected = {HOTKEY_ACTIVATE_ID: 0x77, HOTKEY_VISIBILITY_ID: 0x78}
    with pytest.raises(OSError):
        registration.configure("F8", "F10")
    assert api.keys == expected
    registration.set_paused(True)
    assert api.keys == {}
    registration.set_paused(False)
    assert api.keys == expected
    with pytest.raises(ValueError):
        registration.configure("F8", "F8")
    assert api.keys == expected
    registration.close()
    assert api.keys == {}


def test_wheel_and_focus_return_respect_new_foreground_window():
    class User32:
        foreground = 123

        def GetForegroundWindow(self):
            return self.foreground

        def IsWindow(self, window):
            return True

        def SetForegroundWindow(self, window):
            pytest.fail("must not steal focus back from a different application")

    api = User32()
    received = []
    wheel = GlobalWheelRegistration(
        received.append, user32=api, install=False, window_id=123
    )
    wheel.set_enabled(True)
    assert wheel.dispatch(0x20A, 120 << 16)
    api.foreground = 456
    assert not wheel.dispatch(0x20A, 120 << 16)
    assert received == [120]
    assert not _restore_window_native(api, None, 789, expected_foreground=123)
    wheel.close()


def test_settings_refresh_cancels_recording_and_releases_hotkey_pause():
    app = QApplication.instance() or QApplication([])
    dialog = SetupDialog(AppSettings())
    paused = []
    dialog.recording_changed.connect(paused.append)
    dialog.activation_hotkey.begin_recording()
    dialog.sync_settings(AppSettings())
    assert paused == [True, False]
    assert not dialog.activation_hotkey.is_recording
    dialog.close()
    dialog.deleteLater()
    app.processEvents()


def test_wrapped_message_preserves_every_character_after_emoji(monkeypatch):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFont
    from oopz_overlay.message_widgets import _outlined_text_path

    app = QApplication.instance() or QApplication([])
    drawn = []

    class CapturedPath:
        def addText(self, point, font, text):
            drawn.append(text)

    monkeypatch.setattr("oopz_overlay.message_widgets.QPainterPath", CapturedPath)
    text = "队友😀 已到二楼，请等一下🚩现在从右侧进入，收到✅"
    _outlined_text_path(
        text, QFont("Microsoft YaHei UI", 12), QRectF(0, 0, 110, 300), word_wrap=True
    )
    assert len(drawn) > 1
    assert "".join(drawn) == text
    app.processEvents()


@pytest.mark.skipif(os.name != "nt", reason="requires a Windows message queue")
def test_immediate_exit_does_not_leave_wheel_worker_running():
    for _ in range(3):
        wheel = GlobalWheelRegistration(lambda _: None)
        wheel.close()
        assert not wheel._thread.is_alive()
