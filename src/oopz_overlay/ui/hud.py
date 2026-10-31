from __future__ import annotations
import ctypes
import hashlib
import html
import os
from ctypes import wintypes
from datetime import datetime
from time import monotonic
from PySide6.QtCore import Qt, Signal, QTimer, QEvent, QPoint, QPointF
from PySide6.QtGui import QColor, QPainter, QTextDocument, QFont, QPen, QTextCursor, QTextCharFormat, QImage, QRadialGradient, QLinearGradient
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton
from ..core.state import AppState
from ..core.timeline import Timeline, ChatMessage
from ..i18n import tr
from ..adapters import win32
COLORS = ('#a6c6df', '#c4b1dc', '#a8cbb7', '#dcc49e', '#d7abb4', '#a5ced1')

OUTLINE = '#080b10'


def sample_timeline():
    timeline = Timeline()
    timeline.merge([ChatMessage(f'sample-{i}', 1775000000000000 + i * 1000000,
                               str(i), ('队友 A', 'Mika', '队友 B')[i],
                               tr(f'sample{i + 1}'), False) for i in range(3)],
                   now=monotonic() - 2, live=True)
    return timeline


class Messages(QWidget):

    def __init__(self, parent):
        super().__init__(parent)
        self.timeline = Timeline()
        self.state = AppState()
        self.offset = 0
        self.maximum_offset = 0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = QFont(self.font())
        font.setPointSize(self.state.settings.font_size)
        font.setWeight(QFont.Weight.DemiBold)
        rows = []
        width = max(1, self.width())
        now = monotonic()
        temporary = self.state.mode == 'passive' and not self.state.settings.always_visible
        for message in self.timeline.items:
            alpha = self.timeline.opacity(message.message_id, now=now) if temporary else 1
            if not alpha:
                continue
            color = COLORS[int.from_bytes(hashlib.sha256(message.sender_id.encode()).digest()[:2]) % len(COLORS)]
            timestamp = ''
            if self.offset:
                try:
                    timestamp = datetime.fromtimestamp(message.timestamp_us / 1000000).strftime('%H:%M') + '  '
                except (ValueError, OSError, OverflowError):
                    timestamp = ''
            doc = QTextDocument()
            doc.setDefaultFont(font)
            doc.setDocumentMargin(0)
            doc.setTextWidth(max(1, width - 12))
            text = html.escape(message.text).replace('\n', '<br>')
            doc.setHtml(f'<span style="color:#c0c6d0">{timestamp}</span><span style="color:{color}">{html.escape(message.sender_name)}:</span><span style="color:#ffffff"> {text}</span>')
            rows.append((alpha, doc, doc.size().height() + 7))
        if rows and self.state.mode == 'passive' and self.state.settings.backdrop_opacity:
            # One feathered vignette; every edge dissolves into the game scene.
            backdrop = QImage(self.size(), QImage.Format.Format_ARGB32_Premultiplied)
            backdrop.fill(Qt.GlobalColor.transparent)
            shade = QPainter(backdrop)
            shade.scale(width, max(1, self.height()))
            gradient = QRadialGradient(QPointF(.15, .8), 1)
            dark = QColor(OUTLINE)
            dark.setAlphaF(self.state.settings.backdrop_opacity / 100 * max(row[0] for row in rows))
            gradient.setColorAt(0, dark)
            gradient.setColorAt(1, QColor(0, 0, 0, 0))
            shade.fillRect(0, 0, 1, 1, gradient)
            shade.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            for mask in (QLinearGradient(0, 0, 1, 0), QLinearGradient(0, 0, 0, 1)):
                for at, alpha in ((0, 0), (.08, 255), (.82, 255), (1, 0)):
                    mask.setColorAt(at, QColor(0, 0, 0, alpha))
                shade.fillRect(0, 0, 1, 1, mask)
            shade.end()
            painter.drawImage(0, 0, backdrop)
        total = sum((row[2] for row in rows))
        self.maximum_offset = max(0, int(total - self.height()))
        self.offset = min(self.offset, self.maximum_offset)
        y = self.height() - total + self.offset
        for alpha, doc, height in rows:
            if y + height >= 0 and y < self.height():
                painter.save()
                painter.translate(6, y + 3)
                opacity = self.state.settings.opacity[1] / 100
                shadow = doc.clone()
                cursor = QTextCursor(shadow)
                cursor.select(QTextCursor.SelectionType.Document)
                shade = QTextCharFormat()
                shade.setForeground(QColor(OUTLINE))
                shade.setTextOutline(QPen(QColor(OUTLINE), 5))
                cursor.mergeCharFormat(shade)
                painter.save()
                painter.translate(0, 1.5)
                painter.setOpacity(.2 * alpha)
                shadow.drawContents(painter)
                painter.restore()
                # Draw the dark halo first so text opacity only affects the fill.
                painter.setOpacity(alpha)
                shade.setTextOutline(QPen(QColor(OUTLINE), 3, Qt.PenStyle.SolidLine,
                                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                cursor.mergeCharFormat(shade)
                shadow.drawContents(painter)
                painter.setOpacity(opacity * alpha)
                doc.drawContents(painter)
                painter.restore()
            y += height

class Hud(QWidget):
    action = Signal(str, object)

    def __init__(self, parent=None):
        flags = Qt.WindowType.Widget if parent is not None else Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        super().__init__(parent, flags)
        if parent is None:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMinimumSize(260, 135)
        self.resize(360, 165)
        self.state = AppState()
        self._drag = None
        self._destinations = ()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(5)
        self.messages = Messages(self)
        layout.addWidget(self.messages, 1)
        self.hint = QLabel(self)
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet('color:#e5e7eb;background:rgba(16,19,24,217);padding:4px;')
        layout.addWidget(self.hint)
        self.latest = QPushButton(tr('latest'), self)
        layout.addWidget(self.latest, 0, Qt.AlignmentFlag.AlignRight)
        self.latest.clicked.connect(self.to_latest)
        self.picker = QListWidget(self)
        layout.addWidget(self.picker, 1)
        self.picker.itemActivated.connect(self._choose)
        self.picker.itemClicked.connect(self._choose)
        self.composer = QWidget(self)
        row = QHBoxLayout(self.composer)
        row.setContentsMargins(0, 3, 0, 0)
        row.setSpacing(8)
        self.channel = QLabel(self.composer)
        self.channel.setTextFormat(Qt.TextFormat.PlainText)
        row.addWidget(self.channel)
        self.input = QLineEdit(self.composer)
        self.input.setPlaceholderText(tr('type'))
        self.input.setFrame(False)
        row.addWidget(self.input, 1)
        layout.addWidget(self.composer)
        self.input.textEdited.connect(lambda text: self.action.emit('draft', text))
        self.grip = QLabel('⌟', self)
        self.grip.setFixedSize(18, 18)
        self.grip.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.messages.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.messages.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setStyleSheet('QLabel {color:#9ca3af;background:transparent;} QLineEdit {color:#f0f1f3;background:transparent;padding:3px 0;} QListWidget {color:#e5e7eb;background:transparent;border:0;outline:0;} QListWidget::item {padding:7px;} QListWidget::item:selected {background:#3e454f;} QPushButton {color:#b8c3d1;background:transparent;border:0;}')
        for child in (self.input, self.messages, self.grip, self.picker, self):
            child.installEventFilter(self)
        self._fade = QTimer(self)
        self._fade.setInterval(100)
        self._fade.timeout.connect(self.messages.update)
        self._fade.start()
        self.render(self.state, Timeline(), ())

    def render(self, state: AppState, timeline: Timeline, destinations):
        previous = self.state.mode
        self.state = state
        self.messages.state = state
        self.messages.timeline = timeline
        active = state.mode != 'passive'
        picker = state.mode == 'picker'
        self.messages.setVisible(not picker)
        self.composer.setVisible(state.mode == 'input')
        self.picker.setVisible(picker)
        self.grip.setVisible(active)
        self.channel.setText('#' + state.settings.channel_name)
        self.channel.setMaximumWidth(max(80, self.width() // 3))
        font = self.font()
        font.setPointSize(state.settings.font_size)
        self.input.setFont(font)
        self.picker.setFont(font)
        if self.input.text() != state.draft:
            self.input.setText(state.draft)
        if tuple(destinations) != self._destinations:
            self._destinations = tuple(destinations)
            self.picker.clear()
            for dest in destinations:
                self.picker.addItem(f'{dest.area_name} / #{dest.channel_name}')
            self.picker.setCurrentRow(0)
        hint = ''
        if state.status == 'login':
            hint = tr('login')
        elif not state.settings.channel_id:
            hint = tr('choose', hotkey=state.settings.hotkey)
        elif state.status not in {'connected', ''}:
            hint = tr(state.status)
        if picker and (not destinations):
            hint = tr('login' if state.status == 'login' else 'empty_channels')
        if state.status == 'starting':
            hint = tr('choose', hotkey=state.settings.hotkey)
        if state.mode == 'adjust':
            hint = tr('adjust_hint')
        self.hint.setText(hint)
        self.hint.setVisible(bool(hint))
        if not active:
            self.messages.offset = 0
        self.latest.setVisible(active and (not picker) and (self.messages.offset > 0))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not active)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, not active)
        if self.isWindow() and self.isVisible():
            win32.set_window_click_through(int(self.winId()), not active)
        if active and previous != state.mode:
            (self.picker if picker else self.messages if state.mode == 'adjust' else self.input).setFocus()
        self.messages.update()
        self.update()

    def _choose(self, item):
        row = self.picker.row(item)
        if 0 <= row < len(self._destinations):
            self.action.emit('channel', self._destinations[row])

    def to_latest(self):
        self.messages.offset = 0
        self.latest.hide()
        self.messages.update()

    def handle_wheel(self, delta, control=False):
        if self.state.mode == 'passive':
            return
        if control:
            self.action.emit('font_size', max(9, min(20, self.state.settings.font_size + (1 if delta > 0 else -1))))
        elif self.state.mode == 'picker':
            self.picker.setCurrentRow(max(0, min(self.picker.count() - 1, self.picker.currentRow() + (-1 if delta > 0 else 1))))
        else:
            self.messages.offset = max(0, min(self.messages.maximum_offset, self.messages.offset + int(delta / 120) * 48))
            self.latest.setVisible(self.messages.offset > 0)
            self.messages.update()

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Type.KeyPress and self.state.mode != 'passive':
            key = event.key()
            if key == Qt.Key.Key_Escape:
                if self._drag:
                    self.setGeometry(self._drag[1])
                    self._drag = None
                else:
                    self.action.emit('cancel', None)
                return True
            if key == Qt.Key.Key_Tab and self.state.mode != 'adjust':
                self.action.emit('picker', None)
                return True
            if obj is self.input and event.text() == '#':
                self.action.emit('picker', None)
                return True
            if obj is self.input and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self.input.text().strip():
                    self.action.emit('send', self.input.text())
                return True
        if kind == QEvent.Type.Wheel and self.state.mode != 'passive':
            self.handle_wheel(event.angleDelta().y(), bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier))
            return True
        if obj in (self.messages, self.grip) and self.state.mode != 'passive':
            if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag = (event.globalPosition().toPoint(), self.geometry(), obj is self.grip)
                return True
            if kind == QEvent.Type.MouseMove and self._drag:
                start, rect, resize = self._drag
                delta = event.globalPosition().toPoint() - start
                if resize:
                    self.resize(max(260, rect.width() + delta.x()), max(135, rect.height() + delta.y()))
                else:
                    self.move(rect.topLeft() + delta)
                return True
            if kind == QEvent.Type.MouseButtonRelease and self._drag:
                self._drag = None
                self.action.emit('geometry', self.geometry())
                return True
        if obj is self and kind == QEvent.Type.WindowDeactivate and (self.state.mode != 'passive'):
            self.action.emit('blur', None)
        return super().eventFilter(obj, event)

    def paintEvent(self, event):
        if self.state.mode != 'passive':
            p = QPainter(self)
            p.fillRect(self.rect(), QColor(23, 26, 30, 230))

    def resizeEvent(self, event):
        self.grip.move(self.width() - 20, self.height() - 20)
        super().resizeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self.isWindow():
            win32.set_window_click_through(int(self.winId()), self.state.mode == 'passive')

    def nativeEvent(self, event_type, message):
        if os.name == 'nt':
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == win32.WM_HOTKEY:
                if msg.wParam == win32.HOTKEY_ACTIVATE_ID:
                    self.action.emit('activate', None)
                    return (True, 0)
                if msg.wParam == win32.HOTKEY_VISIBILITY_ID:
                    self.action.emit('toggle', None)
                    return (True, 0)
        return super().nativeEvent(event_type, message)
