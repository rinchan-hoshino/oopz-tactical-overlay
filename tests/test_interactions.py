"""User-visible interaction contracts from the 0.12/1.0 audit."""
from dataclasses import replace

import pytest
from PySide6.QtCore import Qt, QPoint, QEvent
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from oopz_overlay.core.settings import AppSettings
from oopz_overlay.core.state import AppState
from oopz_overlay.core.timeline import Timeline, ChatMessage
from oopz_overlay.ui.hud import Hud


@pytest.fixture
def view():
    app = QApplication.instance() or QApplication([])
    h = Hud()
    h.resize(420, 230)
    timeline = Timeline()
    timeline.merge([ChatMessage(str(i), i * 1000000, 'a', 'Alice',
                                f'Message {i:02d}', False) for i in range(40)],
                   now=0, live=False)
    h.render(AppState(mode='input', connected=True, status='connected',
                      settings=AppSettings(channel_id='c')), timeline, ())
    h.show()
    QTest.qWaitForWindowExposed(h)
    h.activateWindow()
    h.input.setFocus()
    QTest.qWait(50)
    h.messages.grab()
    yield h, app
    h.close()
    h.deleteLater()
    app.processEvents()


@pytest.mark.parametrize('text', ['', '   '])
def test_empty_enter_exits_without_sending(view, text):
    h, app = view
    events = []
    h.action.connect(lambda *args: events.append(args))
    h.input.setText(text)
    QTest.keyClick(h.input, Qt.Key.Key_Return)
    assert events == [('cancel', None)]


@pytest.mark.parametrize('key', [Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape, Qt.Key.Key_Tab])
def test_composition_keys_do_not_send_or_leave_input(view, key):
    h, app = view
    events = []
    h.action.connect(lambda *args: events.append(args))
    h.input.setText('Received ')
    QApplication.sendEvent(h.input, QInputMethodEvent('ni', []))
    QTest.keyClick(h.input, key)
    assert events == []
    commit = QInputMethodEvent()
    commit.setCommitString('你')
    QApplication.sendEvent(h.input, commit)
    QTest.keyClick(h.input, Qt.Key.Key_Return)
    assert events == [('draft', 'Received 你'), ('send', 'Received 你')]


@pytest.mark.parametrize('modifiers', [Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier])
def test_enter_and_shift_enter_send_single_line(view, modifiers):
    h, app = view
    events = []
    h.action.connect(lambda *args: events.append(args))
    QTest.keyClicks(h.input, 'hello')
    QTest.keyClick(h.input, Qt.Key.Key_Return, modifiers)
    assert events[-1] == ('send', 'hello')


def test_latest_visibility_never_changes_messages_geometry_or_pixels(view):
    h, app = view
    h.handle_wheel(120)
    QTest.qWait(220)
    before_rect = h.messages.geometry()
    h.latest.hide()
    app.processEvents()
    without = h.messages.grab().toImage()
    assert h.messages.geometry() == before_rect
    h.latest.show()
    app.processEvents()
    assert h.messages.geometry() == before_rect
    # Compare the text area above the floating control at an unchanged offset.
    with_button = h.messages.grab().toImage()
    height = int((h.messages.height() - h.latest.height() - 12) * without.devicePixelRatio())
    assert without.copy(0, 0, without.width(), height) == with_button.copy(0, 0, with_button.width(), height)
    h.to_latest()
    app.processEvents()
    assert h.messages.geometry() == before_rect


@pytest.mark.parametrize('prune', [False, True])
def test_arriving_messages_keep_history_pixels_anchored(view, prune):
    h, app = view
    h.messages.timeline.limit = 40 if prune else 80
    h.handle_wheel(600)
    QTest.qWait(220)
    before = h.messages.grab().toImage()
    h.messages.timeline.merge([ChatMessage('40', 40000000, 'b', 'Bob',
                                          'New incoming message', False)], now=1, live=True)
    h.render(h.state, h.messages.timeline, ())
    app.processEvents()
    after = h.messages.grab().toImage()
    # Incoming messages change the scroll thumb, but never the text pixels.
    width = int((h.messages.width() - 12) * before.devicePixelRatio())
    assert before.copy(0, 0, width, before.height()) == after.copy(0, 0, width, after.height())
    assert h.messages.offset > 0 and h.latest.isVisible()


def test_latest_follows_new_messages_and_button_returns_keyboard_focus(view):
    h, app = view
    h.messages.timeline.merge([ChatMessage('40', 40000000, 'b', 'Bob', 'new', False)], now=1, live=True)
    h.render(h.state, h.messages.timeline, ())
    app.processEvents()
    assert h.messages.offset == 0 and not h.latest.isVisible()
    h.handle_wheel(120)
    QTest.qWait(220)
    h.latest.setFocus()
    h.latest.click()
    QTest.qWait(220)
    assert h.messages.offset == 0
    assert h.focusWidget() is h.input


def test_small_wheel_deltas_scroll_and_zero_does_not_change_font(view):
    h, app = view
    events = []
    h.action.connect(lambda *args: events.append(args))
    h.handle_wheel(30)
    QTest.qWait(220)
    assert h.messages.offset > 0
    h.handle_wheel(0, control=True)
    assert events == []


def test_leaving_during_drag_does_not_resume_stale_drag(view):
    h, app = view
    origin = h.geometry()
    QTest.mousePress(h.messages, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
    QTest.mouseMove(h.messages, QPoint(45, 40))
    h.render(replace(h.state, mode='passive'), h.messages.timeline, ())
    h.render(replace(h.state, mode='input'), h.messages.timeline, ())
    QTest.mouseMove(h.messages, QPoint(80, 80))
    assert h.geometry() == origin


def test_drag_scrollbar_browses_history_without_resizing_messages(view):
    from PySide6.QtWidgets import QScrollBar, QStyle, QStyleOptionSlider
    h, app = view
    bar = h.messages.findChild(QScrollBar)
    assert bar is not None and bar.isVisible()
    geometry = h.messages.geometry()
    option = QStyleOptionSlider()
    bar.initStyleOption(option)
    thumb = bar.style().subControlRect(QStyle.ComplexControl.CC_ScrollBar, option,
                                      QStyle.SubControl.SC_ScrollBarSlider, bar)
    start = thumb.center()
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(bar, QPoint(start.x(), 8))
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=QPoint(start.x(), 8))
    app.processEvents()
    assert h.messages.offset > 0 and h.latest.isVisible()
    assert h.messages.geometry() == geometry
    h.to_latest()
    app.processEvents()
    assert bar.value() == bar.maximum()


@pytest.mark.parametrize('key', [Qt.Key.Key_PageUp, Qt.Key.Key_Home, Qt.Key.Key_Up])
def test_history_keyboard_navigation_when_messages_have_focus(view, key):
    h, app = view
    h.messages.setFocus()
    QTest.keyClick(h.messages, key)
    QTest.qWait(220)
    assert h.messages.offset > 0
    QTest.keyClick(h.messages, Qt.Key.Key_End)
    QTest.qWait(220)
    assert h.messages.offset == 0


def test_smooth_wheel_accumulates_rapid_notches(view):
    h, app = view
    h.handle_wheel(120)
    h._scroll.setCurrentTime(45)
    assert 0 < h.messages.offset < 48
    h.handle_wheel(120)
    h._scroll.setCurrentTime(130)
    assert h.messages.offset == 96


def test_new_message_stops_inflight_scroll_at_the_reading_anchor(view):
    h, app = view
    h.handle_wheel(600)
    h._scroll.setCurrentTime(45)
    before = h.messages.grab().toImage()
    h.messages.timeline.merge([ChatMessage('40', 40000000, 'b', 'Bob', 'new', False)], now=1, live=True)
    h.render(h.state, h.messages.timeline, ())
    QTest.qWait(200)
    after = h.messages.grab().toImage()
    width = int((h.messages.width() - 12) * before.devicePixelRatio())
    assert before.copy(0, 0, width, before.height()) == after.copy(0, 0, width, after.height())
