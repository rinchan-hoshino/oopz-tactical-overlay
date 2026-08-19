from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QPalette, QWheelEvent
from PySide6.QtWidgets import QApplication

from oopz_overlay.chat import ChatMessage
from oopz_overlay.settings import AppSettings
from oopz_overlay.widgets import (
    MessageRow,
    OutlinedLabel,
    OutlinedLineEdit,
    OverlayWindow,
    _outline_width_for_font,
)
from oopz_overlay.win32_input import HOTKEY_ACTIVATE_ID, WM_HOTKEY


def test_overlay_keeps_the_window_background_transparent(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    focused: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "oopz_overlay.widgets.focus_window",
        lambda window_id, input_id: focused.append((window_id, input_id)) or True,
    )
    window = OverlayWindow()
    window.set_connection_status("#塔科夫战术", True)
    app.processEvents()
    passive_size = window.size()
    assert not window.resize_grip.isVisible()

    window.show_overlay()
    app.processEvents()

    image = window.grab().toImage()
    blank = image.pixelColor(image.width() - 2, 2)
    input_center = window.input.mapTo(window, window.input.rect().center())
    input_line_local = window.input.rect().center()
    input_line_local.setY(window.input.rect().bottom())
    input_line = window.input.mapTo(window, input_line_local)

    assert blank.alpha() == 0
    assert image.pixelColor(input_center).alpha() == window.backdrop_alpha
    assert image.pixelColor(input_line).alpha() > window.backdrop_alpha
    assert window.size() == passive_size
    assert window.height() <= 165
    assert window.width() <= 360
    assert not hasattr(window, "shield")
    assert not window.resize_grip.isVisible()
    assert isinstance(window.input, OutlinedLineEdit)
    assert window.input.hasFocus()
    assert focused

    window.configure(AppSettings(always_visible=False))
    window.hide_overlay()


def test_transparent_input_draws_one_outlined_text_layer_on_native_geometry() -> None:
    app = QApplication.instance() or QApplication([])
    window = OverlayWindow()
    window.set_connection_status("#塔科夫战术", True)
    window.show_overlay()
    window.input.setText("透明描边")
    window.input.setCursorPosition(len(window.input.text()))
    app.processEvents()

    native_text = window.input.palette().color(QPalette.ColorRole.Text)
    assert native_text.alpha() == 0
    assert window.input.rendered_text() == "透明描边"
    expected_origin = (
        window.input.cursorRect().x()
        - window.input.fontMetrics().horizontalAdvance(window.input.text())
    )
    assert abs(window.input.rendered_text_origin_x() - expected_origin) <= 1

    text_image = window.input.grab().toImage()
    window.input.clear()
    empty_image = window.input.grab().toImage()
    text_alpha = sum(
        text_image.pixelColor(x, y).alpha()
        for y in range(text_image.height() - 3)
        for x in range(text_image.width())
    )
    empty_alpha = sum(
        empty_image.pixelColor(x, y).alpha()
        for y in range(empty_image.height() - 3)
        for x in range(empty_image.width())
    )
    assert text_alpha > empty_alpha

    caret = window.input.cursorRect()
    active_empty = window.input.grab().toImage()
    active_caret = active_empty.pixelColor(caret.x(), caret.center().y())
    window.hide_overlay()
    app.processEvents()
    passive_empty = window.input.grab().toImage()
    passive_caret = passive_empty.pixelColor(caret.x(), caret.center().y())
    assert active_caret.alpha() > passive_caret.alpha()

    window.configure(AppSettings(always_visible=False))
    window.hide_overlay()


def test_message_text_uses_yahai_and_a_thin_outline_without_shadow_effects() -> None:
    row = MessageRow(ChatMessage("1", 1, "u", "风屿", "二楼一个", False), font_size=12)
    labels = row.findChildren(OutlinedLabel)
    assert len(labels) == 2
    assert all(label.graphicsEffect() is None for label in labels)
    assert all(label.font().family() == "Microsoft YaHei UI" for label in labels)
    assert all(label.font().pointSize() == 12 for label in labels)
    assert _outline_width_for_font(labels[0].font()) <= 1.5


def test_passive_always_tracks_latest_while_active_preserves_scroll() -> None:
    app = QApplication.instance() or QApplication([])
    window = OverlayWindow()
    window.configure(
        AppSettings(always_visible=True, overlay_width=260, overlay_height=135)
    )
    messages = [
        ChatMessage(str(index), index, "u", "风屿", f"第 {index} 条消息", False)
        for index in range(30)
    ]
    window.merge_messages(messages)
    window.set_connection_status("#塔科夫战术", True)
    app.processEvents()
    scroll_bar = window.history.verticalScrollBar()
    assert scroll_bar.value() == scroll_bar.maximum()
    assert scroll_bar.maximum() > 0

    window.show_overlay()
    app.processEvents()
    scroll_bar.setValue(0)
    window.merge_messages([ChatMessage("31", 31, "u", "风屿", "最新消息", False)])
    app.processEvents()
    assert scroll_bar.value() == 0
    assert scroll_bar.value() < scroll_bar.maximum()

    window.hide_overlay()
    app.processEvents()
    assert scroll_bar.value() == scroll_bar.maximum()

    window.configure(AppSettings(always_visible=False))
    window.hide()


def test_passive_history_is_visible_but_click_through() -> None:
    app = QApplication.instance() or QApplication([])
    window = OverlayWindow()
    window.configure(AppSettings(always_visible=True))
    window.set_connection_status("#塔科夫战术", True)
    app.processEvents()

    assert window.isVisible()
    assert not window.is_active
    assert not hasattr(window, "shield")
    assert window.input.isVisible()
    assert window.input.isEnabled()
    assert window.input.isReadOnly()
    assert window.input.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert not window.resize_grip.isVisible()
    assert window.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    passive_size = window.size()

    window.show_overlay()
    app.processEvents()

    assert window.is_active
    assert window.size() == passive_size
    assert window.input.isVisible()
    assert window.input.isEnabled()
    assert not window.input.isReadOnly()
    assert window.input.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert not window.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert not hasattr(window, "shield")

    window._finish_activation()
    QApplication.sendEvent(window, QEvent(QEvent.Type.WindowDeactivate))
    app.processEvents()
    assert not window.is_active
    assert window.input.isReadOnly()
    assert window.input.focusPolicy() == Qt.FocusPolicy.NoFocus

    window.configure(AppSettings(always_visible=False))
    window.hide_overlay()


def test_history_input_and_drag_surface_share_one_persisted_width() -> None:
    app = QApplication.instance() or QApplication([])
    window = OverlayWindow()
    window.configure(
        AppSettings(always_visible=True, overlay_width=500, overlay_height=240)
    )
    window.set_connection_status("#塔科夫战术", True)
    app.processEvents()

    assert window.width() == 500
    assert window.history.width() == window.input.width()

    window.begin_edit_mode()
    app.processEvents()
    assert window.width() == 500
    assert window.editor.width() == window.width()
    assert window.history.width() == window.input.width()
    window.cancel_edit()

    window.configure(AppSettings(always_visible=False))
    window.hide_overlay()


def test_text_and_backdrop_opacity_apply_to_the_hud() -> None:
    app = QApplication.instance() or QApplication([])
    window = OverlayWindow()
    window.configure(
        AppSettings(
            always_visible=True,
            text_opacity=55,
            backdrop_opacity=40,
        )
    )
    window.merge_messages([ChatMessage("1", 1, "u", "风屿", "二楼一个", False)])
    window.set_connection_status("#塔科夫战术", True)
    app.processEvents()

    row = window.history.itemWidget(window.history.item(0))
    assert row is not None
    labels = row.findChildren(OutlinedLabel)
    assert all(
        label.palette().color(QPalette.ColorRole.WindowText).alpha() == 140
        for label in labels
    )
    assert window.backdrop_alpha == 102

    window.configure(AppSettings(always_visible=False))
    window.hide()


def test_edit_mode_stages_position_and_size_until_done_or_cancel() -> None:
    app = QApplication.instance() or QApplication([])
    window = OverlayWindow()
    window.configure(
        AppSettings(
            always_visible=True,
            position_x=0.5,
            position_y=0.5,
            overlay_width=420,
            overlay_height=220,
        )
    )
    window.set_connection_status("#塔科夫战术", True)
    app.processEvents()
    original = window.geometry()
    committed: list[tuple[float, float, int, int]] = []
    cancelled: list[bool] = []
    window.edit_committed.connect(lambda *values: committed.append(values))
    window.edit_cancelled.connect(lambda: cancelled.append(True))

    window.begin_edit_mode()
    window.move(window.x() + 40, window.y() - 30)
    window.resize(500, 260)
    window.editor.cancel_button.click()
    app.processEvents()

    assert cancelled == [True]
    assert committed == []
    assert window.geometry() == original

    window.begin_edit_mode()
    window.move(window.x() + 20, window.y() - 10)
    window.resize(480, 250)
    window.editor.done_button.click()
    app.processEvents()

    assert len(committed) == 1
    assert committed[0][2:] == (480, 250)
    assert not window.is_editing

    window.configure(AppSettings(always_visible=False))
    window.hide()


def test_font_size_setting_updates_messages_and_the_native_input_editor() -> None:
    app = QApplication.instance() or QApplication([])
    window = OverlayWindow()
    window.configure(AppSettings(always_visible=True, font_size=18))
    window.merge_messages([ChatMessage("1", 1, "u", "风屿", "二楼一个", False)])
    window.set_connection_status("#塔科夫战术", True)
    app.processEvents()

    row = window.history.itemWidget(window.history.item(0))
    assert row is not None
    labels = row.findChildren(OutlinedLabel)
    assert all(label.font().pointSize() == 18 for label in labels)
    assert window.input.font().family() == "Microsoft YaHei UI"
    assert window.input.font().pointSize() == 18

    window.configure(AppSettings(always_visible=False))
    window.hide()


def test_activation_prepares_ime_and_wheel_scrolls_then_exit_returns_to_latest(
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    prepared: list[int] = []
    monkeypatch.setattr(
        "oopz_overlay.widgets.prepare_input_method",
        lambda input_id: prepared.append(input_id) or True,
    )
    window = OverlayWindow()
    window.configure(
        AppSettings(always_visible=True, overlay_width=260, overlay_height=135)
    )
    window.merge_messages(
        [
            ChatMessage(str(index), index, "u", "风屿", f"第 {index} 条", False)
            for index in range(30)
        ]
    )
    window.set_connection_status("#塔科夫战术", True)
    window.show_overlay()
    app.processEvents()

    scroll_bar = window.history.verticalScrollBar()
    assert prepared
    assert scroll_bar.value() == scroll_bar.maximum()
    QApplication.sendEvent(
        window.input,
        QWheelEvent(
            QPointF(10, 10),
            QPointF(10, 10),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        ),
    )
    app.processEvents()
    assert scroll_bar.value() < scroll_bar.maximum()

    window.hide_overlay()
    app.processEvents()
    assert scroll_bar.value() == scroll_bar.maximum()

    window.configure(AppSettings(always_visible=False))
    window.hide()


def test_visible_overlay_reasserts_native_topmost(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    window = OverlayWindow()
    calls: list[int] = []
    monkeypatch.setattr("oopz_overlay.widgets.ensure_window_topmost", calls.append)
    window.set_connection_status("#战术", True)
    window.show_passive()
    app.processEvents()

    window._restore_topmost()

    assert calls[-1] == int(window.winId())
    window.hide()


@pytest.mark.skipif(os.name != "nt", reason="Windows native hotkey message")
def test_native_hotkey_message_emits_activation_signal() -> None:
    window = OverlayWindow()
    emitted: list[bool] = []
    window.activation_hotkey_pressed.connect(lambda: emitted.append(True))
    message = wintypes.MSG()
    message.message = WM_HOTKEY
    message.wParam = HOTKEY_ACTIVATE_ID

    handled, _result = window.nativeEvent(
        b"windows_generic_MSG", ctypes.addressof(message)
    )

    assert handled
    assert emitted == [True]


def test_visibility_toggle_hides_and_restores_passive_hud() -> None:
    app = QApplication.instance() or QApplication([])
    window = OverlayWindow()
    window.configure(AppSettings(always_visible=True))
    window.set_connection_status("#塔科夫战术", True)
    app.processEvents()
    assert window.isVisible()

    window.toggle_visibility()
    app.processEvents()
    assert window.isHidden()

    window.toggle_visibility()
    app.processEvents()
    assert window.isVisible()

    window.configure(AppSettings(always_visible=False))
    window.hide()


def test_enter_sends_text_but_empty_enter_and_escape_cancel() -> None:
    app = QApplication.instance() or QApplication([])
    window = OverlayWindow()
    sent: list[str] = []
    active_when_sent: list[bool] = []
    window.send_requested.connect(
        lambda text: (sent.append(text), active_when_sent.append(window.is_active))
    )
    window.set_connection_status("#塔科夫战术", True)

    window.show_overlay()
    window.input.setText("   ")
    window._submit()
    app.processEvents()
    assert sent == []
    assert not window.is_active
    assert not hasattr(window, "shield")

    window.show_overlay()
    window.input.setText("二楼一个")
    window._submit()
    app.processEvents()
    assert sent == ["二楼一个"]
    assert active_when_sent == [False]
    assert not window.is_active
    assert window.input.isReadOnly()
    QApplication.sendEvent(
        window.input,
        QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.NoModifier,
            "发送后不应继续输入",
        ),
    )
    assert window.input.text() == ""

    window.show_overlay()
    window.input.setText("不发送")
    QApplication.sendEvent(
        window.input,
        QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    app.processEvents()
    assert sent == ["二楼一个"]
    assert not window.is_active

    window.configure(AppSettings(always_visible=False))
    window.hide_overlay()
