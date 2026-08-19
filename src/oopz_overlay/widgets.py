from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import replace
from datetime import UTC, datetime

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QFont,
    QFontMetricsF,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QTextLayout,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizeGrip,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .chat import ChatMessage, ChatTimeline
from .gateway import Destination, LoginResult
from .intent import OverlayAction, OverlayIntent
from .settings import AppSettings
from .win32_input import (
    HOTKEY_ACTIVATE_ID,
    HOTKEY_VISIBILITY_ID,
    WM_HOTKEY,
    ensure_window_topmost,
    focus_window,
    parse_hotkey,
    prepare_input_method,
    set_window_click_through,
)

ACCENT = "#60a5fa"
ACCENT_HOT = "#93c5fd"
TEXT = "#f3f4f6"
MUTED = "#9ca3af"
SURFACE = "#202124"
SURFACE_2 = "#2a2c31"
BORDER = "#3d4046"
DANGER = "#f28b82"
FONT_FAMILY = "Microsoft YaHei UI"


def _ui_font(point_size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont(FONT_FAMILY)
    font.setPointSize(point_size)
    font.setWeight(weight)
    return font


def _with_opacity(color: str, percentage: int) -> QColor:
    value = QColor(color)
    value.setAlpha(round(255 * max(0, min(100, percentage)) / 100))
    return value


_KEY_NAMES = {
    int(Qt.Key.Key_Return): "Enter",
    int(Qt.Key.Key_Enter): "Enter",
    int(Qt.Key.Key_Tab): "Tab",
    int(Qt.Key.Key_Space): "Space",
    int(Qt.Key.Key_Escape): "Escape",
    int(Qt.Key.Key_Delete): "Delete",
    int(Qt.Key.Key_Insert): "Insert",
    int(Qt.Key.Key_Home): "Home",
    int(Qt.Key.Key_End): "End",
    int(Qt.Key.Key_PageUp): "PageUp",
    int(Qt.Key.Key_PageDown): "PageDown",
    int(Qt.Key.Key_Left): "Left",
    int(Qt.Key.Key_Right): "Right",
    int(Qt.Key.Key_Up): "Up",
    int(Qt.Key.Key_Down): "Down",
}


def _hotkey_from_event(event: QKeyEvent) -> str:
    key = int(event.key())
    if int(Qt.Key.Key_A) <= key <= int(Qt.Key.Key_Z):
        key_name = chr(ord("A") + key - int(Qt.Key.Key_A))
    elif int(Qt.Key.Key_0) <= key <= int(Qt.Key.Key_9):
        key_name = chr(ord("0") + key - int(Qt.Key.Key_0))
    elif int(Qt.Key.Key_F1) <= key <= int(Qt.Key.Key_F12):
        key_name = f"F{key - int(Qt.Key.Key_F1) + 1}"
    else:
        key_name = _KEY_NAMES.get(key, "")
    if not key_name:
        raise ValueError("这个按键暂不支持")

    modifiers = event.modifiers()
    parts = []
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        parts.append("Ctrl")
    if modifiers & Qt.KeyboardModifier.AltModifier:
        parts.append("Alt")
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        parts.append("Shift")
    if modifiers & Qt.KeyboardModifier.MetaModifier:
        parts.append("Win")
    parts.append(key_name)
    value = "+".join(parts)
    parse_hotkey(value)
    return value


class HotkeyRecorder(QPushButton):
    hotkey_changed = Signal(str)

    def __init__(self, value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = value
        self.is_recording = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.clicked.connect(self.begin_recording)
        self._show_value()

    def hotkey(self) -> str:
        return self._value

    def set_hotkey(self, value: str) -> None:
        parse_hotkey(value)
        self._value = value
        self.is_recording = False
        self._show_value()

    def begin_recording(self) -> None:
        self.is_recording = True
        self.setText("请按下按键…")
        self.setFocus(Qt.FocusReason.MouseFocusReason)

    def _show_value(self) -> None:
        self.setText(self._value)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self.is_recording:
            super().keyPressEvent(event)
            return
        if event.isAutoRepeat():
            event.accept()
            return
        try:
            value = _hotkey_from_event(event)
        except ValueError:
            event.accept()
            return
        self._value = value
        self.is_recording = False
        self._show_value()
        self.hotkey_changed.emit(value)
        event.accept()

    def focusOutEvent(self, event) -> None:
        if self.is_recording:
            self.is_recording = False
            self._show_value()
        super().focusOutEvent(event)


class SetupDialog(QDialog):
    session_requested = Signal()
    settings_changed = Signal(object)
    edit_requested = Signal()

    def __init__(self, current: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFont(_ui_font(10))
        self.setWindowTitle("Oopz 文字上屏")
        self.setMinimumWidth(540)
        self.setMinimumHeight(650)
        self._base = current
        self._updating = True
        self.setStyleSheet(
            f"""
            QDialog {{ background: {SURFACE}; color: {TEXT}; font-family: "{FONT_FAMILY}"; }}
            QLabel {{ color: {TEXT}; background: transparent; }}
            QLabel#title {{ font: 700 18px "{FONT_FAMILY}"; }}
            QLabel#subtitle, QLabel#updateStatus, QLabel#hint {{ color: {MUTED}; }}
            QLabel#section {{ color: {TEXT}; font: 700 11px "{FONT_FAMILY}"; }}
            QLabel#value {{ color: {ACCENT_HOT}; font-weight: 600; }}
            QFrame#card {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 10px; }}
            QSpinBox, QComboBox, QPushButton {{
                background: #34363c; color: {TEXT}; border: 1px solid #4a4d54;
                border-radius: 7px; padding: 7px 10px; min-height: 22px;
            }}
            QComboBox::drop-down {{ border: 0; width: 28px; }}
            QComboBox QAbstractItemView {{
                background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER};
                selection-background-color: #3b4f73;
            }}
            QSpinBox:hover, QComboBox:hover, QPushButton:hover {{ border-color: #6b707a; }}
            QPushButton:pressed {{ background: #41444b; }}
            QPushButton#primary {{ background: #2563eb; border-color: #3b82f6; color: white; font-weight: 600; }}
            QPushButton#primary:hover {{ background: #2f6ff0; }}
            QSlider::groove:horizontal {{ background: #454850; height: 4px; border-radius: 2px; }}
            QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: #ffffff; border: 2px solid {ACCENT}; width: 14px; margin: -6px 0; border-radius: 8px; }}
            QCheckBox {{ color: {TEXT}; spacing: 8px; }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Oopz 文字上屏")
        title.setObjectName("title")
        titles.addWidget(title)
        subtitle = QLabel("游戏里的 Oopz 文字频道")
        subtitle.setObjectName("subtitle")
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch(1)
        self.version = QLabel(f"v{__version__}")
        self.version.setObjectName("value")
        header.addWidget(self.version, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)
        self.update_status = QLabel("正在检查更新")
        self.update_status.setObjectName("updateStatus")
        root.addWidget(self.update_status)

        connection_card, connection = self._card("Oopz 频道")
        self.server = QLabel("正在读取 Oopz 登录态")
        self.server.setObjectName("value")
        connection.addWidget(self.server)
        self.destination = QComboBox()
        connection.addWidget(self.destination)
        self.sync_button = QPushButton("重新读取服务器和频道")
        connection.addWidget(self.sync_button)
        self.state = QLabel("选择 HUD 要读写的文字频道")
        self.state.setObjectName("hint")
        connection.addWidget(self.state)
        root.addWidget(connection_card)

        shortcut_card, shortcuts = self._card("快捷键")
        self.activation_hotkey = HotkeyRecorder(current.hotkey or "F8")
        shortcuts.addLayout(self._setting_row("输入消息", self.activation_hotkey))
        self.visibility_hotkey = HotkeyRecorder(current.visibility_hotkey or "F9")
        shortcuts.addLayout(
            self._setting_row("显示 / 隐藏 HUD", self.visibility_hotkey)
        )
        hint = QLabel("点击键位，然后直接按下要绑定的按键")
        hint.setObjectName("hint")
        shortcuts.addWidget(hint)
        root.addWidget(shortcut_card)

        appearance_card, appearance = self._card("HUD 外观")
        self.font_size = QSpinBox()
        self.font_size.setRange(9, 20)
        self.font_size.setSuffix(" pt")
        self.font_size.setValue(current.font_size)
        appearance.addLayout(self._setting_row("文字大小", self.font_size))

        self.text_opacity = QSlider(Qt.Orientation.Horizontal)
        self.text_opacity.setRange(20, 100)
        self.text_opacity.setValue(current.text_opacity)
        self.text_opacity_value = QLabel(f"{current.text_opacity}%")
        self.text_opacity_value.setObjectName("value")
        appearance.addLayout(
            self._slider_row("文字透明度", self.text_opacity, self.text_opacity_value)
        )

        self.backdrop_opacity = QSlider(Qt.Orientation.Horizontal)
        self.backdrop_opacity.setRange(0, 85)
        self.backdrop_opacity.setValue(current.backdrop_opacity)
        self.backdrop_opacity_value = QLabel(f"{current.backdrop_opacity}%")
        self.backdrop_opacity_value.setObjectName("value")
        appearance.addLayout(
            self._slider_row(
                "背景遮罩",
                self.backdrop_opacity,
                self.backdrop_opacity_value,
            )
        )
        self.always_visible = QCheckBox("连接后显示 HUD")
        self.always_visible.setChecked(current.always_visible)
        appearance.addWidget(self.always_visible)
        self.edit_button = QPushButton("编辑 HUD 位置与大小")
        self.edit_button.setObjectName("primary")
        appearance.addWidget(self.edit_button)
        root.addWidget(appearance_card)
        root.addStretch(1)

        self.edit_button.clicked.connect(self._request_edit)
        self.sync_button.clicked.connect(self._read_session)
        self.destination.currentIndexChanged.connect(self._emit_current)
        self.activation_hotkey.hotkey_changed.connect(self._emit_current)
        self.visibility_hotkey.hotkey_changed.connect(self._emit_current)
        self.font_size.valueChanged.connect(self._emit_current)
        self.text_opacity.valueChanged.connect(self._text_opacity_changed)
        self.backdrop_opacity.valueChanged.connect(self._backdrop_opacity_changed)
        self.always_visible.toggled.connect(self._emit_current)

        self._populate_current_destination(current)
        self._updating = False

    @staticmethod
    def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("section")
        layout.addWidget(heading)
        return card, layout

    @staticmethod
    def _setting_row(title: str, control: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(title))
        row.addStretch(1)
        control.setMinimumWidth(150)
        row.addWidget(control)
        return row

    @staticmethod
    def _slider_row(title: str, slider: QSlider, value: QLabel) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(title))
        row.addWidget(slider, 1)
        value.setMinimumWidth(42)
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(value)
        return row

    def _populate_current_destination(self, current: AppSettings) -> None:
        self.destination.clear()
        if current.area_id:
            self.server.setText(current.area_name or "上次选择的服务器")
        if current.area_id and current.channel_id:
            destination = Destination(
                current.area_id,
                current.area_name or "当前服务器",
                current.channel_id,
                current.channel_name or "当前频道",
            )
            self.destination.addItem(destination.label, destination)
        else:
            self.destination.addItem("正在读取频道…", None)

    def _read_session(self) -> None:
        self.sync_button.setEnabled(False)
        self.sync_button.setText("正在读取…")
        self.state.setText("正在读取 Oopz 登录态和频道列表")
        self.session_requested.emit()

    def apply_login_result(self, result: LoginResult) -> None:
        self._updating = True
        self._base = result.settings
        current_key = (result.settings.area_id, result.settings.channel_id)
        self.server.setText(result.current_area_name or "未检测到当前语音服务器")
        self.destination.clear()
        self.destination.addItem("请选择文字频道", None)
        selected = 0
        for destination in result.destinations:
            self.destination.addItem(destination.label, destination)
            if (destination.area_id, destination.channel_id) == current_key:
                selected = self.destination.count() - 1
        if not result.destinations:
            self.destination.setItemText(0, "请先加入 Oopz 语音服务器")
        self.destination.setCurrentIndex(selected)
        self.sync_button.setEnabled(True)
        self.sync_button.setText("重新读取服务器和频道")
        self.state.setText("手动选择 HUD 要读写的文字频道")
        self._updating = False

    def show_error(self, message: str) -> None:
        self.sync_button.setEnabled(True)
        self.sync_button.setText("重新读取服务器和频道")
        self.server.setText("Oopz 未连接")
        self.state.setText(message)

    def set_update_status(self, text: str) -> None:
        self.update_status.setText(text)

    def sync_settings(self, settings: AppSettings) -> None:
        self._base = settings

    def _request_edit(self) -> None:
        self.hide()
        self.edit_requested.emit()

    def _text_opacity_changed(self, value: int) -> None:
        self.text_opacity_value.setText(f"{value}%")
        self._emit_current()

    def _backdrop_opacity_changed(self, value: int) -> None:
        self.backdrop_opacity_value.setText(f"{value}%")
        self._emit_current()

    def _emit_current(self) -> None:
        if self._updating:
            return
        hotkey = self.activation_hotkey.hotkey()
        visibility_hotkey = self.visibility_hotkey.hotkey()
        try:
            parse_hotkey(hotkey)
            parse_hotkey(visibility_hotkey)
        except ValueError:
            return
        destination = self.destination.currentData()
        updates = {
            "hotkey": hotkey,
            "visibility_hotkey": visibility_hotkey,
            "always_visible": self.always_visible.isChecked(),
            "font_size": self.font_size.value(),
            "text_opacity": self.text_opacity.value(),
            "backdrop_opacity": self.backdrop_opacity.value(),
            "area_id": "",
            "area_name": "",
            "channel_id": "",
            "channel_name": "",
        }
        if isinstance(destination, Destination):
            updates.update(
                area_id=destination.area_id,
                area_name=destination.area_name,
                channel_id=destination.channel_id,
                channel_name=destination.channel_name,
            )
        self._base = replace(self._base, **updates)
        self.settings_changed.emit(self._base)


class DragSurface(QLabel):
    moved = Signal(QPoint)

    def __init__(self) -> None:
        super().__init__("拖动调整位置")
        self._offset = QPoint()
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"color:{TEXT}; background:transparent; font:600 10px '{FONT_FAMILY}';"
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._offset = event.globalPosition().toPoint()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            current = event.globalPosition().toPoint()
            self.moved.emit(current - self._offset)
            self._offset = current
            event.accept()


class EditorBar(QFrame):
    moved = Signal(QPoint)
    cancelled = Signal()
    accepted = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("hudEditor")
        self.setStyleSheet(
            f"""
            QFrame#hudEditor {{ background: rgba(32,33,36,242); border: 1px solid {ACCENT}; border-radius: 8px; }}
            QPushButton {{ background: #34363c; color: {TEXT}; border: 1px solid #5a5d65; border-radius: 5px; padding: 5px 12px; }}
            QPushButton#done {{ background: #2563eb; border-color: #3b82f6; color: white; }}
            """
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)
        self.drag_surface = DragSurface()
        self.drag_surface.moved.connect(self.moved.emit)
        layout.addWidget(self.drag_surface, 1)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.cancelled.emit)
        layout.addWidget(self.cancel_button)
        self.done_button = QPushButton("完成")
        self.done_button.setObjectName("done")
        self.done_button.clicked.connect(self.accepted.emit)
        layout.addWidget(self.done_button)


def _outlined_text_path(
    text: str,
    font: QFont,
    rect: QRectF,
    *,
    word_wrap: bool,
    x_override: float | None = None,
) -> QPainterPath:
    path = QPainterPath()
    if not text:
        return path
    metrics = QFontMetricsF(font)
    if not word_wrap:
        x = rect.left() if x_override is None else x_override
        baseline = (
            rect.top() + (rect.height() - metrics.height()) / 2 + metrics.ascent()
        )
        path.addText(QPointF(x, baseline), font, text)
        return path

    layout = QTextLayout(text, font)
    layout.beginLayout()
    y = 0.0
    lines = []
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(max(1.0, rect.width()))
        line.setPosition(QPointF(0.0, y))
        lines.append(line)
        y += line.height()
    layout.endLayout()
    for line in lines:
        segment = text[line.textStart() : line.textStart() + line.textLength()]
        baseline = rect.top() + line.y() + line.ascent()
        path.addText(QPointF(rect.left() + line.x(), baseline), font, segment)
    return path


def _outline_width_for_font(font: QFont) -> float:
    point_size = font.pointSizeF()
    if point_size <= 0:
        point_size = 12.0
    return max(1.0, min(1.7, point_size * 0.1))


def _paint_outlined_path(
    painter: QPainter,
    path: QPainterPath,
    fill: QColor,
    stroke_width: float,
) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    stroke = QColor("#000000")
    stroke.setAlpha(fill.alpha())
    painter.strokePath(
        path,
        QPen(
            stroke,
            stroke_width,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        ),
    )
    painter.fillPath(path, fill)


class OutlinedLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setContentsMargins(2, 1, 2, 1)

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setClipRect(self.contentsRect())
        path = _outlined_text_path(
            self.text(),
            self.font(),
            QRectF(self.contentsRect()),
            word_wrap=self.wordWrap(),
        )
        _paint_outlined_path(
            painter,
            path,
            self.palette().color(QPalette.ColorRole.WindowText),
            _outline_width_for_font(self.font()),
        )


class OutlinedLineEdit(QLineEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._preedit = ""
        self._text_opacity = 100
        palette = self.palette()
        transparent = QColor(0, 0, 0, 0)
        palette.setColor(QPalette.ColorRole.Text, transparent)
        palette.setColor(QPalette.ColorRole.HighlightedText, transparent)
        palette.setColor(QPalette.ColorRole.PlaceholderText, transparent)
        self.setPalette(palette)

    def inputMethodEvent(self, event) -> None:
        super().inputMethodEvent(event)
        self._preedit = event.preeditString()
        self.update()

    def set_text_opacity(self, percentage: int) -> None:
        self._text_opacity = max(20, min(100, percentage))
        self.update()

    def rendered_text(self) -> str:
        text = self.text()
        if not self._preedit:
            return text
        cursor = self.cursorPosition()
        return f"{text[:cursor]}{self._preedit}{text[cursor:]}"

    def rendered_text_origin_x(self) -> float:
        cursor = self.cursorPosition()
        prefix = self.text()[:cursor]
        if self._preedit:
            prefix += self._preedit
        return float(self.cursorRect().x()) - QFontMetricsF(
            self.font()
        ).horizontalAdvance(prefix)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        rendered = self.rendered_text()
        content_rect = QRectF(self.contentsRect())
        painter = QPainter(self)
        painter.setClipRect(content_rect)
        path = _outlined_text_path(
            rendered,
            self.font(),
            content_rect,
            word_wrap=False,
            x_override=self.rendered_text_origin_x(),
        )
        _paint_outlined_path(
            painter,
            path,
            _with_opacity(TEXT, self._text_opacity),
            _outline_width_for_font(self.font()),
        )
        if self.hasFocus() and not self.isReadOnly():
            cursor_rect = self.cursorRect()
            painter.fillRect(
                cursor_rect.x(),
                cursor_rect.y(),
                max(2, cursor_rect.width()),
                cursor_rect.height(),
                QColor(ACCENT_HOT),
            )


class MessageRow(QWidget):
    def __init__(
        self,
        message: ChatMessage,
        font_size: int = 12,
        text_opacity: int = 100,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 1, 3, 1)
        layout.setSpacing(6)

        moment = ""
        if message.timestamp_us:
            seconds = message.timestamp_us / 1_000_000
            moment = (
                datetime.fromtimestamp(seconds, tz=UTC).astimezone().strftime("%H:%M")
            )
        sender = OutlinedLabel(f"{moment}  {message.sender_name}")
        sender.setFont(_ui_font(font_size, QFont.Weight.Bold))
        sender_palette = sender.palette()
        sender_palette.setColor(
            QPalette.ColorRole.WindowText,
            _with_opacity(ACCENT_HOT if message.mine else "#b7c4b1", text_opacity),
        )
        sender.setPalette(sender_palette)
        sender.setStyleSheet("background:transparent;")
        text = OutlinedLabel(message.text)
        text.setWordWrap(True)
        text.setMaximumWidth(570)
        text.setFont(_ui_font(font_size))
        text_palette = text.palette()
        text_palette.setColor(
            QPalette.ColorRole.WindowText,
            _with_opacity(TEXT, text_opacity),
        )
        text.setPalette(text_palette)
        text.setStyleSheet("background:transparent;")
        layout.addWidget(sender, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(text, 0, Qt.AlignmentFlag.AlignTop)
        layout.addStretch(1)


class OverlayWindow(QWidget):
    send_requested = Signal(str)
    settings_requested = Signal()
    activation_hotkey_pressed = Signal()
    visibility_hotkey_pressed = Signal()
    edit_committed = Signal(float, float, int, int)
    edit_cancelled = Signal()

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFont(_ui_font(10))
        self.setWindowTitle("Oopz Tactical Link")
        self.timeline = ChatTimeline(limit=80)
        self.intent = OverlayIntent()
        self._connected = False
        self._settings = AppSettings()
        self._active = False
        self._editing = False
        self._user_hidden = False
        self._edit_original = None
        self._activation_guard = False
        self.setMinimumSize(260, 135)
        self._resize_render_timer = QTimer(self)
        self._resize_render_timer.setSingleShot(True)
        self._resize_render_timer.setInterval(60)
        self._resize_render_timer.timeout.connect(self._render_timeline)
        self._topmost_timer = QTimer(self)
        self._topmost_timer.setInterval(750)
        self._topmost_timer.timeout.connect(self._restore_topmost)
        self._topmost_timer.start()

        root = QVBoxLayout(self)
        root.setContentsMargins(5, 3, 5, 3)
        root.setSpacing(2)

        self.status = QLabel("")
        self.status.setStyleSheet(
            f'color:{DANGER}; font:700 10px "{FONT_FAMILY}"; background:transparent;'
        )
        self.status.hide()
        root.addWidget(self.status)

        self.history = QListWidget()
        self.history.setFrameShape(QListWidget.Shape.NoFrame)
        self.history.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.history.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.history.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.history.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.history.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.history.setStyleSheet(
            "QListWidget { background: transparent; border: none; outline: none; }"
            "QListWidget::item { background: transparent; border: none; }"
        )
        root.addWidget(self.history, 1)

        self.input = OutlinedLineEdit()
        self.input.setMaxLength(500)
        self.input.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.input.setReadOnly(True)
        self.input.returnPressed.connect(self._submit)
        self.input.installEventFilter(self)
        self.history.viewport().installEventFilter(self)
        self.input.setStyleSheet(
            """
            QLineEdit {
                background: transparent; color: transparent; border: none;
                border-bottom: 1px solid rgba(185,163,106,180);
                border-radius: 0; padding: 4px 8px;
                selection-background-color: rgba(185,163,106,170);
                selection-color: transparent;
            }
            QLineEdit:focus { border-bottom: 2px solid #e2c36f; }
            QLineEdit:disabled { color: transparent; border-bottom: 1px solid rgba(185,163,106,105); }
            """
        )
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(0)
        input_row.addWidget(self.input, 1)
        root.addLayout(input_row)
        self.resize_grip = QSizeGrip(self)
        self.resize_grip.setFixedSize(18, 18)
        self.resize_grip.hide()
        self.editor = EditorBar(self)
        self.editor.hide()
        self.editor.moved.connect(lambda delta: self.move(self.pos() + delta))
        self.editor.cancelled.connect(self.cancel_edit)
        self.editor.accepted.connect(self.commit_edit)
        self._position_floating_controls()
        self._apply_font_size(self._settings.font_size)

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def is_editing(self) -> bool:
        return self._editing

    @property
    def backdrop_alpha(self) -> int:
        return round(255 * self._settings.backdrop_opacity / 100)

    def configure(self, settings: AppSettings) -> None:
        self._settings = settings
        self._apply_font_size(settings.font_size)
        self.input.set_text_opacity(settings.text_opacity)
        self.update()
        if self._editing:
            return
        if self.isVisible() and self._active:
            self._place_window()
        elif settings.always_visible and self._connected and not self._user_hidden:
            self.show_passive()
        else:
            self.hide()

    def set_connection_status(self, text: str, connected: bool) -> None:
        self._connected = connected
        self.input.setReadOnly(not (connected and self._active))
        self.status.setText(text)
        self.status.setVisible(bool(text) and not connected and self._active)
        if (
            connected
            and self._settings.always_visible
            and not self._active
            and not self._user_hidden
        ):
            self.show_passive()
        elif not connected and not self._active:
            self.hide()

    def merge_messages(self, messages: list[ChatMessage]) -> None:
        if not self.timeline.merge(messages):
            return
        self._render_timeline()

    def clear_messages(self) -> None:
        self.timeline = ChatTimeline(limit=80)
        self.history.clear()

    def _render_timeline(self, *, force_latest: bool = False) -> None:
        scroll_bar = self.history.verticalScrollBar()
        was_latest = scroll_bar.value() >= scroll_bar.maximum() - 2
        previous_scroll = scroll_bar.value()
        self.history.clear()
        row_width = max(200, self.history.viewport().width())
        for message in self.timeline.items:
            item = QListWidgetItem()
            row = MessageRow(
                message,
                font_size=self._settings.font_size,
                text_opacity=self._settings.text_opacity,
            )
            row.setFixedWidth(row_width)
            row.layout().activate()
            item.setSizeHint(QSize(row_width, row.sizeHint().height() + 3))
            self.history.addItem(item)
            self.history.setItemWidget(item, row)
        if force_latest or not self._active or was_latest:
            self.history.scrollToBottom()
            QTimer.singleShot(0, self.history.scrollToBottom)
        else:

            def restore_scroll() -> None:
                scroll_bar.setValue(min(previous_scroll, scroll_bar.maximum()))

            restore_scroll()
            QTimer.singleShot(0, restore_scroll)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        alpha = self.backdrop_alpha
        if alpha <= 0 and not self._editing:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(8, 10, 14, max(alpha, 155) if self._editing else alpha)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(self.rect().adjusted(3, 3, -3, -3), 9, 9)

    def _apply_font_size(self, font_size: int) -> None:
        self.input.setFont(_ui_font(font_size))
        input_height = QFontMetricsF(self.input.font()).height() + 16
        self.input.setFixedHeight(max(35, round(input_height)))
        if self.timeline.items:
            self._render_timeline()

    def _restore_topmost(self) -> None:
        if self.isVisible():
            ensure_window_topmost(int(self.winId()))

    def _set_interactive(self, interactive: bool) -> None:
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, not interactive
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, not interactive)
        if self.isVisible():
            set_window_click_through(int(self.winId()), not interactive)

    def _place_window(self) -> None:
        screen = self.screen()
        area = screen.availableGeometry()
        default_width = min(360, max(260, int(area.width() * 0.21)))
        default_height = min(165, max(135, int(area.height() * 0.2)))
        width = self._settings.overlay_width or default_width
        height = self._settings.overlay_height or default_height
        width = max(260, min(width, area.width()))
        height = max(135, min(height, area.height()))
        self.resize(width, height)
        center_x = area.left() + round(area.width() * self._settings.position_x)
        center_y = area.top() + round(area.height() * self._settings.position_y)
        x = center_x - width // 2
        y = center_y - height // 2
        x = max(area.left(), min(x, area.right() - width + 1))
        y = max(area.top(), min(y, area.bottom() - height + 1))
        self.move(x, y)

    def show_passive(self) -> None:
        if (
            not self._settings.always_visible
            or not self._connected
            or self._user_hidden
        ):
            self._active = False
            self.hide()
            return
        self._active = False
        self._editing = False
        self.editor.hide()
        self.resize_grip.hide()
        self.status.hide()
        self.input.clearFocus()
        self.input.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.input.setReadOnly(True)
        self.input.clear()
        self.input.setPlaceholderText("")
        self.input.setEnabled(self._connected)
        self._place_window()
        self._render_timeline(force_latest=True)
        self._set_interactive(False)
        self.show()
        self._set_interactive(False)
        self._restore_topmost()

    def show_overlay(self) -> None:
        self._active = True
        self._editing = False
        self._activation_guard = True
        self.editor.hide()
        self.input.setEnabled(self._connected)
        self.input.setReadOnly(not self._connected)
        self.input.setPlaceholderText("")
        self.status.setVisible(not self._connected)
        self._place_window()
        self._render_timeline(force_latest=True)
        self.resize_grip.hide()
        self.input.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._set_interactive(True)
        self.show()
        self._set_interactive(True)
        self._restore_topmost()
        self._focus_input()
        QTimer.singleShot(80, self._focus_input)
        QTimer.singleShot(160, self._finish_activation)

    def _finish_activation(self) -> None:
        self._activation_guard = False

    def _focus_input(self) -> None:
        if not self._active:
            return
        self.raise_()
        self.activateWindow()
        self.input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        focus_window(int(self.winId()), int(self.input.winId()))
        prepare_input_method(int(self.input.winId()))

    def begin_edit_mode(self) -> None:
        self._active = False
        self._editing = True
        self._edit_original = self.geometry()
        self._place_window()
        self.editor.show()
        self.editor.raise_()
        self.resize_grip.show()
        self.resize_grip.raise_()
        self.status.hide()
        self.input.clearFocus()
        self.input.setReadOnly(True)
        self.input.setEnabled(False)
        self._render_timeline(force_latest=True)
        self._set_interactive(True)
        self.show()
        self._set_interactive(True)
        self._restore_topmost()
        self.raise_()
        self.update()

    def cancel_edit(self) -> None:
        if not self._editing:
            return
        original = self._edit_original
        self._editing = False
        self._edit_original = None
        if original is not None:
            self.setGeometry(original)
        self.editor.hide()
        self.resize_grip.hide()
        self.input.setEnabled(self._connected)
        self.show_passive()
        self.edit_cancelled.emit()

    def commit_edit(self) -> None:
        if not self._editing:
            return
        area = self.screen().availableGeometry()
        center = self.geometry().center()
        x = (center.x() - area.left()) / max(1, area.width())
        y = (center.y() - area.top()) / max(1, area.height())
        width = self.width()
        height = self.height()
        self._editing = False
        self._edit_original = None
        self.editor.hide()
        self.resize_grip.hide()
        self.input.setEnabled(self._connected)
        self.edit_committed.emit(
            max(0.0, min(1.0, x)),
            max(0.0, min(1.0, y)),
            width,
            height,
        )
        self.show_passive()

    def hide_overlay(self) -> None:
        self._active = False
        self._activation_guard = False
        self.input.clearFocus()
        self.input.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.input.setReadOnly(True)
        self.resize_grip.hide()
        self.history.scrollToBottom()
        QTimer.singleShot(0, self.history.scrollToBottom)
        if self._settings.always_visible and self._connected and not self._user_hidden:
            self.show_passive()
        else:
            self.hide()

    def toggle_visibility(self) -> None:
        self._user_hidden = not self._user_hidden
        if self._user_hidden:
            self._active = False
            self._activation_guard = False
            self.input.clear()
            self.input.clearFocus()
            self.hide()
        else:
            self.show_passive()

    def nativeEvent(self, event_type, message):
        if os.name == "nt":
            native_message = ctypes.cast(
                int(message), ctypes.POINTER(wintypes.MSG)
            ).contents
            if native_message.message == WM_HOTKEY:
                identifier = int(native_message.wParam)
                if identifier == HOTKEY_ACTIVATE_ID:
                    self.activation_hotkey_pressed.emit()
                    return True, 0
                if identifier == HOTKEY_VISIBILITY_ID:
                    self.visibility_hotkey_pressed.emit()
                    return True, 0
        return super().nativeEvent(event_type, message)

    def event(self, event) -> bool:
        if (
            event.type() == QEvent.Type.WindowDeactivate
            and getattr(self, "_active", False)
            and not getattr(self, "_editing", False)
            and not getattr(self, "_activation_guard", False)
        ):
            self.input.clear()
            self.hide_overlay()
        return super().event(event)

    def _submit(self) -> None:
        decision = self.intent.enter(
            hidden=False, target_active=False, draft=self.input.text()
        )
        text = decision.text
        should_send = decision.action is OverlayAction.SEND_AND_HIDE and bool(text)
        self.input.clear()
        self.hide_overlay()
        if should_send:
            self.send_requested.emit(text)

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self.input
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
        ):
            self.input.clear()
            self.hide_overlay()
            return True
        if (
            self._active
            and watched in {self.input, self.history.viewport()}
            and event.type() == QEvent.Type.Wheel
        ):
            delta = event.angleDelta().y()
            if delta:
                scroll_bar = self.history.verticalScrollBar()
                step = max(40, scroll_bar.pageStep() // 3)
                scroll_bar.setValue(scroll_bar.value() - (step if delta > 0 else -step))
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.input.clear()
            self.hide_overlay()
            event.accept()
            return
        super().keyPressEvent(event)

    def _position_floating_controls(self) -> None:
        self.resize_grip.move(
            self.width() - self.resize_grip.width() - 3,
            self.height() - self.resize_grip.height() - 3,
        )
        self.editor.setGeometry(0, 0, self.width(), self.editor.sizeHint().height())
        self.resize_grip.raise_()
        self.editor.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "resize_grip"):
            self._position_floating_controls()
        if hasattr(self, "_resize_render_timer") and self.isVisible():
            self._resize_render_timer.start()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.hide_overlay()
        event.ignore()
