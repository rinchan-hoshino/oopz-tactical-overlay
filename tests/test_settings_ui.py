from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QSlider, QSpinBox

from oopz_overlay import __version__
from oopz_overlay.settings import AppSettings
from oopz_overlay.widgets import HotkeyRecorder, SetupDialog


def test_settings_use_direct_controls_and_show_read_only_oopz_channel() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = SetupDialog(AppSettings())
    observed: list[AppSettings] = []
    dialog.settings_changed.connect(observed.append)
    dialog.show()
    app.processEvents()

    dialog.set_current_channel("综合文字", connected=True)

    assert dialog.windowTitle() == "Oopz 文字上屏"
    assert dialog.version.text() == f"v{__version__}"
    assert dialog.current_channel.text() == "#综合文字"
    assert not hasattr(dialog, "destination")
    assert not hasattr(dialog, "sync_button")
    assert isinstance(dialog.activation_hotkey, HotkeyRecorder)
    assert isinstance(dialog.visibility_hotkey, HotkeyRecorder)
    assert isinstance(dialog.font_size, QSpinBox)
    assert isinstance(dialog.text_opacity, QSlider)
    assert isinstance(dialog.backdrop_opacity, QSlider)

    dialog.font_size.setValue(18)
    dialog.text_opacity.setValue(72)
    dialog.backdrop_opacity.setValue(38)
    app.processEvents()

    assert observed[-1].font_size == 18
    assert observed[-1].text_opacity == 72
    assert observed[-1].backdrop_opacity == 38

    dialog.close()


def test_hotkey_recorder_captures_the_keys_actually_pressed() -> None:
    app = QApplication.instance() or QApplication([])
    recorder = HotkeyRecorder("F8")
    changed: list[str] = []
    recorder.hotkey_changed.connect(changed.append)
    recorder.show()
    recorder.click()
    QApplication.sendEvent(
        recorder,
        QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_K,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
            "k",
        ),
    )
    app.processEvents()

    assert recorder.hotkey() == "Ctrl+Alt+K"
    assert changed == ["Ctrl+Alt+K"]
    assert not recorder.is_recording

    recorder.close()


def test_hud_editor_is_an_explicit_staged_action() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = SetupDialog(AppSettings())
    requested: list[bool] = []
    dialog.edit_requested.connect(lambda: requested.append(True))
    dialog.show()

    dialog.edit_button.click()
    app.processEvents()

    assert requested == [True]
    assert dialog.isHidden()
    dialog.close()
