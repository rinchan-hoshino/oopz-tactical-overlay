from __future__ import annotations
import ctypes
import hashlib
import html
import os
from ctypes import wintypes
from datetime import datetime
from time import monotonic
from PySide6.QtCore import Qt, Signal, QTimer, QEvent, QPoint, QPointF, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QTextDocument, QFont, QPen, QTextCursor, QTextCharFormat, QImage, QRadialGradient, QLinearGradient
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QScrollBar
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
    browsing_changed = Signal(bool)
    scroll_changed = Signal(int, int)

    def __init__(self, parent):
        super().__init__(parent)
        self.timeline = Timeline()
        self.state = AppState()
        self.offset = 0
        self.maximum_offset = 0
        self._items = ()
        self._anchor = None
        self._browsing = False
        self._scroll_metrics = (0, 0)

    def _set_scroll_offset(self, value):
        self.offset = value
        self.update()

    scroll_offset = Property(int, lambda self: self.offset, _set_scroll_offset)

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
        items = self.timeline.items
        for message in items:
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
            doc.setTextWidth(max(1, width - 24))
            text = html.escape(message.text).replace('\n', '<br>')
            doc.setHtml(f'<span style="color:#c0c6d0">{timestamp}</span><span style="color:{color}">{html.escape(message.sender_name)}:</span><span style="color:#ffffff"> {text}</span>')
            rows.append((alpha, doc, doc.size().height() + 7, message.message_id))
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
        if self.offset and items != self._items and self._anchor:
            anchor_id, anchor_y = self._anchor
            y = self.height() - total
            for _, _, height, message_id in rows:
                if message_id == anchor_id:
                    self.offset = max(0, round(anchor_y - y))
                    break
                y += height
        self._items = items
        self.offset = min(self.offset, self.maximum_offset)
        y = self.height() - total + self.offset
        self._anchor = None
        for alpha, doc, height, message_id in rows:
            if y + height >= 0 and y < self.height():
                if self._anchor is None:
                    self._anchor = (message_id, y)
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
        browsing = self.offset > 0
        if browsing != self._browsing:
            self._browsing = browsing
            self.browsing_changed.emit(browsing)
        metrics = (self.offset, self.maximum_offset)
        if metrics != self._scroll_metrics:
            self._scroll_metrics = metrics
            self.scroll_changed.emit(*metrics)

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
        self._composing = False
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
        self.latest = QPushButton(tr('latest'), self.messages)
        self.latest.setStyleSheet('color:#e5e7eb;background:#252b35;padding:4px 8px;border-radius:4px;')
        self.latest.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.latest.clicked.connect(self.to_latest)
        self.messages.browsing_changed.connect(self.latest.setVisible)
        self.scrollbar = QScrollBar(Qt.Orientation.Vertical, self.messages)
        self.scrollbar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scrollbar.setStyleSheet('QScrollBar:vertical {background:transparent;width:8px;} QScrollBar::handle:vertical {background:#687382;border-radius:4px;min-height:16px;} QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;} QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {background:transparent;}')
        self.scrollbar.valueChanged.connect(self._scroll_to)
        self.messages.scroll_changed.connect(self._sync_scrollbar)
        self._scroll = QPropertyAnimation(self.messages, b'scroll_offset', self)
        self._scroll.setDuration(130)
        self._scroll.setEasingCurve(QEasingCurve.Type.OutCubic)
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
        if self.messages.offset and timeline.items != self.messages._items:
            # Keep the last painted reading anchor when incoming traffic changes rows.
            self._scroll.stop()
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
            self._scroll.stop()
            if self._drag:
                self.setGeometry(self._drag[1])
                self._drag = None
            self.messages.offset = 0
        if state.mode != 'input':
            self._composing = False
            self.input.clearFocus()
        self.latest.setVisible(active and (not picker) and (self.messages.offset > 0))
        self._sync_scrollbar(self.messages.offset, self.messages.maximum_offset)
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
        self._scroll.stop()
        self.messages.offset = 0
        self.latest.hide()
        self.messages.update()
        if self.state.mode == 'input':
            self.input.setFocus(Qt.FocusReason.MouseFocusReason)

    def _sync_scrollbar(self, offset, maximum):
        self.scrollbar.blockSignals(True)
        self.scrollbar.setRange(0, maximum)
        self.scrollbar.setPageStep(self.messages.height())
        self.scrollbar.setValue(maximum - offset)
        self.scrollbar.blockSignals(False)
        self.scrollbar.setVisible(self.state.mode in {'input', 'adjust'} and maximum > 0)

    def _scroll_to(self, value):
        self._scroll.stop()
        self.messages.offset = self.messages.maximum_offset - value
        self.messages.update()

    def handle_wheel(self, delta, control=False):
        if self.state.mode == 'passive' or not delta:
            return
        if control:
            self.action.emit('font_size', max(9, min(20, self.state.settings.font_size + (1 if delta > 0 else -1))))
        elif self.state.mode == 'picker':
            self.picker.setCurrentRow(max(0, min(self.picker.count() - 1, self.picker.currentRow() + (-1 if delta > 0 else 1))))
        else:
            base = self._scroll.endValue() if self._scroll.state() == QPropertyAnimation.State.Running else self.messages.offset
            distance = round(delta / 120 * 48) or (1 if delta > 0 else -1)
            target = max(0, min(self.messages.maximum_offset, base + distance))
            self._scroll.stop()
            self._scroll.setStartValue(self.messages.offset)
            self._scroll.setEndValue(target)
            self._scroll.start()

    def eventFilter(self, obj, event):
        kind = event.type()
        if obj is self.messages and kind == QEvent.Type.Resize:
            self.latest.adjustSize()
            self.latest.move(max(0, self.messages.width() - self.latest.width() - 12),
                             max(0, self.messages.height() - self.latest.height() - 4))
            self.scrollbar.setGeometry(max(0, self.messages.width() - 8), 0, 8, self.messages.height())
        if obj is self.input and kind == QEvent.Type.InputMethod:
            self._composing = bool(event.preeditString())
        if kind == QEvent.Type.KeyPress and self.state.mode != 'passive':
            if self._composing:
                return False
            key = event.key()
            if obj is self.messages:
                if key in (Qt.Key.Key_Home, Qt.Key.Key_End):
                    self._scroll_to(0 if key == Qt.Key.Key_Home else self.messages.maximum_offset)
                    return True
                steps = {Qt.Key.Key_Up: 120, Qt.Key.Key_Down: -120,
                         Qt.Key.Key_PageUp: self.messages.height() / 48 * 120,
                         Qt.Key.Key_PageDown: -self.messages.height() / 48 * 120}
                if key in steps:
                    self.handle_wheel(steps[key])
                    return True
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
                else:
                    self.action.emit('cancel', None)
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
