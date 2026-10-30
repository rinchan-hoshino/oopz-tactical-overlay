from dataclasses import replace
import pytest
from PySide6.QtCore import Qt, QPoint, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from oopz_overlay.core.state import AppState, reduce
from oopz_overlay.core.settings import AppSettings
from oopz_overlay.core.timeline import Timeline, ChatMessage
from oopz_overlay.ui.hud import Hud
from oopz_overlay.ui.settings_window import SettingsWindow

@pytest.fixture(scope='session')
def qapp():
    return QApplication.instance() or QApplication([])

@pytest.fixture
def hud(qapp):
    h=Hud(); h.show(); qapp.processEvents()
    yield h
    h.close()

def test_three_modes_and_first_run(hud,qapp):
    s=AppState()
    hud.render(s, Timeline(), ())
    assert not hud.composer.isVisible() and not hud.picker.isVisible()
    assert s.settings.hotkey in hud.hint.text()
    hud.render(reduce(s,'activate'), Timeline(), ())
    assert hud.picker.isVisible() and not hud.composer.isVisible()
    s=replace(s,mode='input',settings=AppSettings(channel_id='c',channel_name='战术'))
    hud.render(s,Timeline(),())
    assert hud.composer.isVisible() and hud.channel.text() == '#战术'

def test_keyboard_picker_send_cancel(hud,qapp):
    events=[]
    hud.action.connect(lambda *args: events.append(args))
    s=AppState(mode='input', settings=AppSettings(channel_id='c'))
    hud.render(s,Timeline(),())
    hud.input.setFocus(); QTest.keyClicks(hud.input,'hello')
    QTest.keyClick(hud.input,Qt.Key.Key_Tab)
    assert events[-1][0] == 'picker'
    QTest.keyClick(hud.input,Qt.Key.Key_Return)
    assert ('send','hello') in events
    QTest.keyClick(hud.input,Qt.Key.Key_Escape)
    assert events[-1][0] == 'cancel'

def test_hash_opens_picker_without_sending(hud,qapp):
    events=[]; hud.action.connect(lambda *args: events.append(args))
    hud.render(AppState(mode='input',settings=AppSettings(channel_id='c')),Timeline(),())
    QTest.keyClicks(hud.input,'#')
    assert ('picker',None) in events
    assert hud.input.text() == ''

def test_scroll_and_ctrl_wheel(hud,qapp):
    t=Timeline()
    t.merge([ChatMessage(str(i),i,'a','Alice','message '+str(i),False) for i in range(40)],now=0,live=False)
    hud.render(AppState(mode='input',settings=AppSettings(channel_id='c')),t,())
    events=[]; hud.action.connect(lambda *args: events.append(args))
    qapp.processEvents()
    hud.handle_wheel(120,False)
    assert hud.messages.offset > 0 and hud.latest.isVisible()
    hud.handle_wheel(120,True)
    assert events[-1] == ('font_size',13)
    hud.latest.click()
    assert hud.messages.offset == 0

def test_drag_release_saves_and_escape_rolls_back(hud,qapp):
    hud.render(AppState(mode='input',settings=AppSettings(channel_id='c')),Timeline(),())
    events=[]; hud.action.connect(lambda *args: events.append(args))
    origin=hud.geometry()
    QTest.mousePress(hud.messages,Qt.MouseButton.LeftButton,pos=QPoint(20,20))
    QTest.mouseMove(hud.messages,QPoint(40,35))
    QTest.keyClick(hud.input,Qt.Key.Key_Escape)
    QTest.mouseRelease(hud.messages,Qt.MouseButton.LeftButton,pos=QPoint(40,35))
    assert hud.geometry() == origin
    assert not any(e[0]=='geometry' for e in events)
    QTest.mousePress(hud.grip,Qt.MouseButton.LeftButton,pos=QPoint(4,4))
    QTest.mouseMove(hud.grip,QPoint(45,30))
    QTest.mouseRelease(hud.grip,Qt.MouseButton.LeftButton,pos=QPoint(45,30))
    assert any(e[0]=='geometry' for e in events)

def test_settings_small_single_page_emits_live_changes(qapp):
    w=SettingsWindow(AppSettings()); w.show(); qapp.processEvents()
    edits=[]; w.changed.connect(edits.append)
    w.strength.setValue(65); w.font_size.setValue(16)
    assert edits[-1].font_size == 16 and edits[-1].strength == 65
    assert w.width() < 500 and w.height() < 420
    w.close()
