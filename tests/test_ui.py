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
    QTest.qWait(180)
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

def test_settings_independent_display_controls(qapp):
    w=SettingsWindow(AppSettings()); w.show(); qapp.processEvents()
    edits=[]; w.changed.connect(edits.append)
    w.text_opacity.setValue(65); w.backdrop_opacity.setValue(40); w.font_size.setValue(16)
    w.always_visible.setChecked(False)
    assert edits[-1].font_size == 16 and edits[-1].text_opacity == 65
    assert edits[-1].backdrop_opacity == 40 and not edits[-1].always_visible
    w.close()


def test_settings_lists_all_sounds_and_preserves_unavailable_selection(qapp, monkeypatch):
    from oopz_overlay.ui import settings_window as module
    choices = [(f'Alarm{i}', f'Alarm{i}.wav') for i in range(1, 11)] + [
        ('Windows Notify', 'Windows Notify.wav'), ('Theme/Chime', 'Theme/Chime.wav')]
    monkeypatch.setattr(module, 'system_sounds', lambda: choices)
    w = SettingsWindow(AppSettings(notification_sound='missing.wav'))
    assert w.sound.count() == 14
    assert w.sound.findData('Windows Notify.wav') >= 0
    assert w.sound.findData('Theme/Chime.wav') >= 0
    assert w.sound.currentData() == 'missing.wav'
    assert not w.listen.isEnabled()
    w.sound.setCurrentIndex(w.sound.findData('Windows Notify.wav'))
    assert w.listen.isEnabled()
    w.close()


def test_preview_uses_real_hud_and_updates_without_changing_live_history(qapp):
    w = SettingsWindow(AppSettings())
    w.show(); qapp.processEvents()
    assert w.preview.hud.messages.timeline.items
    w.text_opacity.setValue(77)
    assert w.preview.hud.state.settings.text_opacity == 77
    w.scene.setCurrentIndex(1)
    assert w.preview.scene == 'black'
    assert w.width() <= 480 and w.height() < 650
    w.close()


@pytest.mark.parametrize('aged', [False, True])
def test_message_rendering_has_solid_outline_and_readable_fill(qapp, aged):
    from time import monotonic
    from oopz_overlay.ui.hud import Messages
    from PySide6.QtGui import QColor
    w = Messages(None); w.resize(400, 90)
    w.state = AppState(settings=AppSettings(font_size=18, backdrop_opacity=0))
    w.timeline.merge([ChatMessage('m', 1, '4', 'Mika', 'Test message', False)],
                     now=monotonic() - (30 if aged else 2), live=True)
    w.show(); qapp.processEvents()
    img = w.grab().toImage()
    colors = [img.pixelColor(x,y) for y in range(img.height()) for x in range(img.width())]
    assert sum(c.alpha() > 240 and max(c.red(),c.green(),c.blue()) < 35 for c in colors) > 70
    # The full glyph interiors remain bright even after passive fading.
    assert sum(c.alpha() > 240 and min(c.red(),c.green(),c.blue()) > 155 for c in colors) > 25
    w.close()


@pytest.mark.parametrize('sender', ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'])
@pytest.mark.parametrize('age', [0, 30])
def test_name_halo_contrast_over_white_for_new_and_old_messages(qapp, sender, age):
    import hashlib
    from collections import Counter
    from time import monotonic
    from PySide6.QtGui import QColor, QImage, QPainter
    from oopz_overlay.ui.hud import Messages, COLORS, OUTLINE
    w = Messages(None)
    w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    w.resize(320, 70)
    w.state = AppState(settings=AppSettings(backdrop_opacity=0))
    w.timeline.merge([ChatMessage('m', 1, sender, 'MMMM', 'Readable text', False)],
                     now=monotonic() - age, live=True)
    w.show(); qapp.processEvents()
    img = QImage(w.size(), QImage.Format.Format_ARGB32)
    img.fill(QColor('white'))
    painter = QPainter(img); painter.drawPixmap(0, 0, w.grab()); painter.end()
    colors = Counter(img.pixelColor(x, y).rgb() for y in range(img.height()) for x in range(img.width()))
    colors.pop(QColor('white').rgb(), None)
    background = QColor(OUTLINE)
    # The contrasting halo, rather than the game scene, borders each glyph.
    assert colors[background.rgb()] > 20
    assert sum(count for rgb, count in colors.items()
               if max(QColor(rgb).getRgb()[:3]) < 35) < 2000
    foreground = QColor(COLORS[int.from_bytes(hashlib.sha256(sender.encode()).digest()[:2]) % len(COLORS)])
    assert sum(count for rgb, count in colors.items()
               if max(abs(a-b) for a,b in zip(QColor(rgb).getRgb()[:3], foreground.getRgb()[:3])) <= 3) > 2
    def luminance(c):
        values = [v / 255 for v in c.getRgb()[:3]]
        return sum(weight * (v / 12.92 if v <= .04045 else ((v+.055)/1.055)**2.4)
                   for weight, v in zip((.2126, .7152, .0722), values))
    assert (luminance(foreground)+.05)/(luminance(background)+.05) >= 4.5
    w.close()


def test_text_opacity_changes_glyph_fill_but_keeps_outline(qapp):
    from time import monotonic
    from oopz_overlay.ui.hud import Messages
    w = Messages(None); w.resize(300, 70)
    w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    w.state = AppState(settings=AppSettings(font_size=18, backdrop_opacity=0))
    w.timeline.merge([ChatMessage('m', 1, '4', 'MMMM', 'MMMM', False)], now=monotonic()-2, live=True)
    w.show(); qapp.processEvents()
    bright = w.grab().toImage()
    w.state = replace(w.state, settings=replace(w.state.settings, text_opacity=20))
    dim = w.grab().toImage()
    def count(image, minimum):
        return sum(min(image.pixelColor(x,y).getRgb()[:3]) > minimum
                   for y in range(image.height()) for x in range(image.width()))
    assert count(bright, 160) > count(dim, 160) + 50
    assert sum(dim.pixelColor(x,y).alpha() > 240 and max(dim.pixelColor(x,y).getRgb()[:3]) < 35
               for y in range(dim.height()) for x in range(dim.width())) > 50
    w.close()


def test_embedded_hud_keeps_normal_child_painting_and_no_native_clickthrough(qapp, monkeypatch):
    from PySide6.QtWidgets import QWidget
    from oopz_overlay.ui.hud import sample_timeline
    from oopz_overlay.adapters import win32
    calls = []
    monkeypatch.setattr(win32, 'set_window_click_through', lambda *args: calls.append(args))
    parent = QWidget(); parent.resize(400, 150)
    h = Hud(parent); h.setGeometry(parent.rect())
    h.render(AppState(status=''), sample_timeline(), ())
    parent.show(); qapp.processEvents()
    h.render(AppState(status=''), sample_timeline(), ())
    assert not h.isWindow()
    assert not h.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert not calls
    parent.close()


def test_preview_keeps_three_samples_visible_at_largest_font(qapp):
    w = SettingsWindow(AppSettings(font_size=20))
    w.show(); qapp.processEvents()
    assert w.preview.hud.messages.maximum_offset == 0
    w.close()


def test_passive_hud_background_is_a_soft_vignette_not_message_ribbons(qapp):
    from oopz_overlay.ui.hud import sample_timeline
    h = Hud(); h.resize(500, 220)
    h.render(AppState(status='', settings=AppSettings(channel_id='c', backdrop_opacity=20)),
             sample_timeline(), ())
    h.show(); qapp.processEvents()
    image = h.grab().toImage()
    # Blank space between rows is shaded too, and shading dissolves at the edges.
    assert 0 < image.pixelColor(45, 65).alpha() <= 51
    assert image.pixelColor(45, 65).alpha() > image.pixelColor(450, 65).alpha()
    assert image.pixelColor(250, 9).alpha() == 0
    h.render(replace(h.state, settings=replace(h.state.settings, backdrop_opacity=0)),
             h.messages.timeline, ())
    qapp.processEvents()
    image = h.grab().toImage()
    assert image.pixelColor(45, 65).alpha() == 0
    h.close()


@pytest.mark.parametrize('connected', [True, False])
def test_nonpersistent_messages_and_their_background_fade_together(qapp, monkeypatch, connected):
    from oopz_overlay.ui import hud as module
    now = 100.0
    monkeypatch.setattr(module, 'monotonic', lambda: now)
    h = Hud(); h.resize(400, 160)
    timeline = Timeline()
    timeline.merge([ChatMessage('m', 1, 'a', 'Alice', 'Incoming message', False)], now=now, live=True)
    h.render(AppState(connected=connected, status='connected' if connected else 'reconnecting', settings=AppSettings(
        channel_id='c', always_visible=False)), timeline, ())
    h.show(); qapp.processEvents()
    def alpha():
        image = h.grab().toImage()
        rect = h.messages.geometry()
        scale = image.devicePixelRatio()
        image = image.copy(int(rect.x()*scale), int(rect.y()*scale),
                           int(rect.width()*scale), int(rect.height()*scale))
        return sum(image.pixelColor(x,y).alpha() for y in range(image.height()) for x in range(image.width()))
    fresh = alpha()
    now = 109.0
    halfway = alpha()
    assert 0 < halfway < fresh * .8
    now = 111.0
    assert alpha() == 0
    h.render(replace(h.state, mode='input'), timeline, ())
    assert alpha() > 0
    h.render(replace(h.state, mode='passive', settings=replace(h.state.settings, always_visible=True)), timeline, ())
    qapp.processEvents()
    assert alpha() >= fresh
    h.close()
