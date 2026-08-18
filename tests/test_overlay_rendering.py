from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QPalette
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
    assert window.resize_grip.isVisible()

    window.show_overlay()
    app.processEvents()

    image = window.grab().toImage()
    blank = image.pixelColor(image.width() - 2, 2)
    input_center = window.input.mapTo(window, window.input.rect().center())
    input_line_local = window.input.rect().center()
    input_line_local.setY(window.input.rect().bottom())
    input_line = window.input.mapTo(window, input_line_local)

    assert blank.alpha() == 0
    assert image.pixelColor(input_center).alpha() == 0
    assert image.pixelColor(input_line).alpha() > 0
    assert window.size() == passive_size
    assert window.height() <= 165
    assert window.width() <= 360
    assert not hasattr(window, "shield")
    assert window.resize_grip.isVisible()
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
    assert window.resize_grip.isVisible()
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

    window.begin_drag_mode()
    app.processEvents()
    assert window.width() == 500
    assert window.drag_handle.width() == window.history.width()
    assert window.drag_handle.width() == window.input.width()

    window.configure(AppSettings(always_visible=False))
    window.hide_overlay()


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
