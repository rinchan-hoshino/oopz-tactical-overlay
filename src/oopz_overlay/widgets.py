from __future__ import annotations

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
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .chat import ChatMessage, ChatTimeline
from .gateway import Destination, LoginResult
from .intent import OverlayAction, OverlayIntent
from .settings import AppSettings
from .win32_input import focus_window, parse_hotkey, set_window_click_through

ACCENT = "#b9a36a"
ACCENT_HOT = "#d6bd78"
TEXT = "#e4dfd2"
MUTED = "#85877e"
SURFACE = "#111412"
SURFACE_2 = "#1a1e1a"
BORDER = "#4b5047"
DANGER = "#c86f61"
FONT_FAMILY = "Microsoft YaHei UI"


def _ui_font(point_size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont(FONT_FAMILY)
    font.setPointSize(point_size)
    font.setWeight(weight)
    return font


class SetupDialog(QDialog):
    session_requested = Signal()
    settings_changed = Signal(object)
    drag_requested = Signal()

    def __init__(self, current: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFont(_ui_font(10))
        self.setWindowTitle("Tactical Link")
        self.setMinimumWidth(460)
        self._base = current
        self._updating = True
        self.setStyleSheet(
            f"""
            QDialog {{ background: {SURFACE}; color: {TEXT}; font-family: "{FONT_FAMILY}"; }}
            QLabel {{ color: {TEXT}; font-family: "{FONT_FAMILY}"; }}
            QLabel#title {{ color: {ACCENT_HOT}; font: 700 18px "{FONT_FAMILY}"; }}
            QLabel#section {{ color: {MUTED}; font: 700 10px "{FONT_FAMILY}"; letter-spacing: 1px; }}
            QLabel#version {{ color: {ACCENT}; font: 700 10px "{FONT_FAMILY}"; }}
            QLabel#updateStatus {{ color: {MUTED}; font: 10px "Microsoft YaHei UI"; }}
            QComboBox {{
                background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER};
                border-radius: 0; padding: 8px 10px; min-height: 22px;
            }}
            QComboBox::drop-down {{ border: 0; width: 28px; }}
            QComboBox QAbstractItemView {{
                background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER};
                selection-background-color: #37382e;
            }}
            QPushButton[action="true"] {{
                background: transparent; color: {ACCENT}; border: 1px solid {BORDER};
                border-radius: 0; padding: 7px 10px; text-align: left;
            }}
            QPushButton[action="true"]:hover {{ border-color: {ACCENT}; color: {ACCENT_HOT}; }}
            QPushButton[action="true"]:pressed {{ background: #27291f; }}
            QCheckBox {{ color: {TEXT}; spacing: 8px; }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 20)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("TACTICAL LINK  //  OOPZ")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch(1)
        self.version = QLabel(f"v{__version__}")
        self.version.setObjectName("version")
        header.addWidget(self.version)
        self.state = QLabel("LOCAL")
        self.state.setStyleSheet(f'color:{MUTED}; font:10px "{FONT_FAMILY}";')
        header.addWidget(self.state)
        root.addLayout(header)
        self.update_status = QLabel("更新 // 等待自动检查")
        self.update_status.setObjectName("updateStatus")
        root.addWidget(self.update_status)
        root.addSpacing(6)

        root.addWidget(self._section("CURRENT OOPZ SERVER"))
        self.server = QLabel("未检测到当前服务器")
        self.server.setStyleSheet(
            f"color:{ACCENT_HOT}; font:700 13px 'Microsoft YaHei UI';"
        )
        root.addWidget(self.server)
        self.destination = QComboBox()
        root.addWidget(self.destination)
        self.sync_button = QPushButton("↻  重新检测当前服务器")
        self.sync_button.setProperty("action", True)
        root.addWidget(self.sync_button)

        root.addSpacing(6)
        root.addWidget(self._section("INPUT"))
        self.hotkey = QComboBox()
        self.hotkey.addItems(["F8", "F9", "F10", "Enter"])
        self.hotkey.setCurrentText(current.hotkey or "F8")
        root.addWidget(self.hotkey)

        self.font_size = QComboBox()
        for size in range(9, 21):
            self.font_size.addItem(f"HUD 字号  {size} pt", size)
        selected_font_size = self.font_size.findData(current.font_size)
        self.font_size.setCurrentIndex(max(0, selected_font_size))
        root.addWidget(self.font_size)

        self.always_visible = QCheckBox("常显")
        self.always_visible.setChecked(current.always_visible)
        root.addWidget(self.always_visible)

        self.drag_button = QPushButton("↔  拖动 HUD 位置")
        self.drag_button.setProperty("action", True)
        root.addWidget(self.drag_button)

        self.sync_button.clicked.connect(self._read_session)
        self.drag_button.clicked.connect(self.drag_requested.emit)
        self.destination.currentIndexChanged.connect(self._emit_current)
        self.hotkey.currentTextChanged.connect(self._emit_current)
        self.font_size.currentIndexChanged.connect(self._emit_current)
        self.always_visible.toggled.connect(self._emit_current)

        self._populate_current_destination(current)
        self._updating = False

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("section")
        return label

    def _populate_current_destination(self, current: AppSettings) -> None:
        self.destination.clear()
        if current.area_id:
            self.server.setText(current.area_name or "上次检测的服务器")
        if current.area_id and current.channel_id:
            destination = Destination(
                current.area_id,
                current.area_name or "当前服务器",
                current.channel_id,
                current.channel_name or "当前频道",
            )
            self.destination.addItem(destination.label, destination)
        else:
            self.destination.addItem("请先加入 Oopz 语音频道", None)

    def _read_session(self) -> None:
        self.sync_button.setEnabled(False)
        self.sync_button.setText("正在同步…")
        self.state.setText("SYNC")
        self.session_requested.emit()

    def apply_login_result(self, result: LoginResult) -> None:
        self._updating = True
        self._base = result.settings
        current_key = (result.settings.area_id, result.settings.channel_id)
        destinations = list(result.destinations)
        self.server.setText(result.current_area_name or "未检测到当前 Oopz 语音服务器")

        self.destination.clear()
        selected = -1
        for destination in destinations:
            self.destination.addItem(destination.label, destination)
            if (destination.area_id, destination.channel_id) == current_key:
                selected = self.destination.count() - 1
        if not destinations:
            self.destination.addItem("请先加入 Oopz 语音频道", None)
        elif selected >= 0:
            self.destination.setCurrentIndex(selected)
        else:
            self.destination.setCurrentIndex(0)
        self.sync_button.setEnabled(True)
        self.sync_button.setText("↻  重新检测当前服务器")
        self.state.setText("READY")
        self._updating = False
        self._emit_current()

    def show_error(self, message: str) -> None:
        self.sync_button.setEnabled(True)
        self.sync_button.setText("↻  重新检测当前服务器")
        self.state.setText("ERROR")
        QMessageBox.warning(self, "同步失败", message)

    def set_update_status(self, text: str) -> None:
        self.update_status.setText(text)

    def _emit_current(self) -> None:
        if self._updating:
            return
        destination = self.destination.currentData()
        hotkey = self.hotkey.currentText().strip()
        try:
            parse_hotkey(hotkey)
        except ValueError:
            return
        updates = {
            "hotkey": hotkey,
            "always_visible": self.always_visible.isChecked(),
            "font_size": int(self.font_size.currentData()),
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


class DragHandle(QLabel):
    moved = Signal(QPoint)
    released = Signal()

    def __init__(self) -> None:
        super().__init__("MOVE HUD  //  拖动后松开")
        self._offset = QPoint()
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"background:rgba(16,18,15,220); color:{ACCENT_HOT};"
            f'border:1px solid {ACCENT}; padding:5px; font:700 10px "{FONT_FAMILY}";'
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

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.released.emit()
            event.accept()


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
    painter.strokePath(
        path,
        QPen(
            QColor("#000000"),
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
            QColor(TEXT),
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
        sender = OutlinedLabel(f"[{moment}] {message.sender_name} //")
        sender.setFont(_ui_font(font_size, QFont.Weight.Bold))
        sender.setStyleSheet(
            f"color:{ACCENT_HOT if message.mine else '#a8b8a0'};background:transparent;"
        )
        text = OutlinedLabel(message.text)
        text.setWordWrap(True)
        text.setMaximumWidth(570)
        text.setFont(_ui_font(font_size))
        text.setStyleSheet(f"color:{TEXT}; background:transparent;")
        layout.addWidget(sender, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(text, 0, Qt.AlignmentFlag.AlignTop)
        layout.addStretch(1)


class OverlayWindow(QWidget):
    send_requested = Signal(str)
    settings_requested = Signal()
    position_changed = Signal(float, float)
    size_changed = Signal(int, int)

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
        self._dragging = False
        self._activation_guard = False
        self.setMinimumSize(260, 135)
        self._resize_render_timer = QTimer(self)
        self._resize_render_timer.setSingleShot(True)
        self._resize_render_timer.setInterval(60)
        self._resize_render_timer.timeout.connect(self._render_timeline)

        root = QVBoxLayout(self)
        root.setContentsMargins(5, 3, 5, 3)
        root.setSpacing(2)

        self.drag_handle = DragHandle()
        self.drag_handle.hide()
        self.drag_handle.moved.connect(lambda delta: self.move(self.pos() + delta))
        self.drag_handle.released.connect(self._finish_drag)
        root.addWidget(self.drag_handle)

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
        self.resize_grip.setFixedSize(16, 16)
        self.resize_grip.hide()
        self._position_resize_grip()
        self._apply_font_size(self._settings.font_size)

    @property
    def is_active(self) -> bool:
        return self._active

    def configure(self, settings: AppSettings) -> None:
        self._settings = settings
        self._apply_font_size(settings.font_size)
        if self._dragging:
            return
        if self.isVisible() and self._active:
            self._place_window()
        elif settings.always_visible and self._connected:
            self.show_passive()
        else:
            self.hide()

    def set_connection_status(self, text: str, connected: bool) -> None:
        self._connected = connected
        self.input.setReadOnly(not (connected and self._active))
        self.status.setText(text)
        self.status.setVisible(bool(text) and not connected and self._active)
        if connected and self._settings.always_visible and not self._active:
            self.show_passive()
        elif not connected and not self._active:
            self.hide()

    def merge_messages(self, messages: list[ChatMessage]) -> None:
        if not self.timeline.merge(messages):
            return
        self._render_timeline()

    def _render_timeline(self, *, force_latest: bool = False) -> None:
        scroll_bar = self.history.verticalScrollBar()
        was_latest = scroll_bar.value() >= scroll_bar.maximum() - 2
        previous_scroll = scroll_bar.value()
        self.history.clear()
        row_width = max(200, self.history.viewport().width())
        for message in self.timeline.items:
            item = QListWidgetItem()
            row = MessageRow(message, font_size=self._settings.font_size)
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

    def _apply_font_size(self, font_size: int) -> None:
        self.input.setFont(_ui_font(font_size))
        input_height = QFontMetricsF(self.input.font()).height() + 16
        self.input.setFixedHeight(max(35, round(input_height)))
        if self.timeline.items:
            self._render_timeline()

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
        if not self._settings.always_visible or not self._connected:
            self._active = False
            self.hide()
            return
        self._active = False
        self._dragging = False
        self.drag_handle.hide()
        self.resize_grip.show()
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

    def show_overlay(self) -> None:
        self._active = True
        self._dragging = False
        self._activation_guard = True
        self.drag_handle.hide()
        self.input.setEnabled(self._connected)
        self.input.setReadOnly(not self._connected)
        self.input.setPlaceholderText("")
        self.status.setVisible(not self._connected)
        self._place_window()
        self._render_timeline(force_latest=True)
        self.resize_grip.show()
        self.input.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._set_interactive(True)
        self.show()
        self._set_interactive(True)
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

    def begin_drag_mode(self) -> None:
        self._active = False
        self._dragging = True
        self._place_window()
        self.drag_handle.show()
        self.resize_grip.hide()
        self.status.hide()
        self.input.setReadOnly(True)
        self.input.setEnabled(False)
        self.input.setPlaceholderText("")
        self._render_timeline(force_latest=True)
        self._set_interactive(True)
        self.show()
        self._set_interactive(True)
        self.raise_()

    def _finish_drag(self) -> None:
        area = self.screen().availableGeometry()
        center = self.geometry().center()
        x = (center.x() - area.left()) / max(1, area.width())
        y = (center.y() - area.top()) / max(1, area.height())
        self._dragging = False
        self.position_changed.emit(max(0.0, min(1.0, x)), max(0.0, min(1.0, y)))
        self.show_passive()

    def hide_overlay(self) -> None:
        remembered_size = self.size() if self._active else None
        self._active = False
        self._activation_guard = False
        self.input.clearFocus()
        self.input.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.input.setReadOnly(True)
        self.resize_grip.hide()
        if self._settings.always_visible and self._connected:
            self.show_passive()
        else:
            self.hide()
        if remembered_size is not None:
            self.size_changed.emit(remembered_size.width(), remembered_size.height())

    def event(self, event) -> bool:
        if (
            event.type() == QEvent.Type.WindowDeactivate
            and getattr(self, "_active", False)
            and not getattr(self, "_dragging", False)
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
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.input.clear()
            self.hide_overlay()
            event.accept()
            return
        super().keyPressEvent(event)

    def _position_resize_grip(self) -> None:
        self.resize_grip.move(
            self.width() - self.resize_grip.width(),
            self.height() - self.resize_grip.height(),
        )
        self.resize_grip.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "resize_grip"):
            self._position_resize_grip()
        if hasattr(self, "_resize_render_timer") and self.isVisible():
            self._resize_render_timer.start()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.hide_overlay()
        event.ignore()
