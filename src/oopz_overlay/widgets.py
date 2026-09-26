from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from time import monotonic

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QFontMetricsF,
    QGuiApplication,
    QMouseEvent,
    QPainter,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from .chat import ChatMessage, ChatTimeline
from .intent import OverlayAction, OverlayIntent
from .settings import AppSettings
from .win32_input import (
    HOTKEY_ACTIVATE_ID,
    HOTKEY_VISIBILITY_ID,
    WM_HOTKEY,
    ensure_window_topmost,
    focus_window,
    foreground_window,
    prepare_input_method,
    restore_window,
    set_window_click_through,
)

from .ui_common import (
    APP_NAME,
    ACCENT,
    TEXT,
    DANGER,
    FONT_FAMILY,
    _ui_font,
)
from .settings_dialog import (
    HotkeyRecorder as HotkeyRecorder,
    SetupDialog as SetupDialog,
)

from .message_widgets import (
    HistoryNavigation,
    message_time,
    MessageComposer,
    MessageRow as MessageRow,
    OutlinedLabel as OutlinedLabel,
    OutlinedLineEdit as OutlinedLineEdit,
    _outline_width_for_font as _outline_width_for_font,
)


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
            QPushButton#done {{ background: #b4c68b; border-color: #b4c68b; color: #20281a; }}
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


class OverlayWindow(QWidget):
    send_requested = Signal(str)
    settings_requested = Signal()
    activation_hotkey_pressed = Signal()
    visibility_hotkey_pressed = Signal()
    edit_committed = Signal(float, float, int, int)
    edit_cancelled = Signal()
    interaction_changed = Signal(bool)
    activation_failed = Signal(str)

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFont(_ui_font(10))
        self._native_windows = (
            os.name == "nt"
            and QGuiApplication.platformName() not in {"offscreen", "minimal"}
        )
        self.setWindowTitle(f"{APP_NAME} · 消息")
        self.timeline = ChatTimeline(limit=80)
        self.intent = OverlayIntent()
        self._connected = False
        self._settings = AppSettings()
        self._active = False
        self._editing = False
        self._user_hidden = False
        self._edit_original = None
        self._activation_guard = False
        self._return_window_id = 0
        self._highlight_until: dict[str, float] = {}
        self.setMinimumSize(260, 135)
        self._resize_render_timer = QTimer(self)
        self._resize_render_timer.setSingleShot(True)
        self._resize_render_timer.setInterval(60)
        self._resize_render_timer.timeout.connect(self._render_timeline)
        self._rendered_rows = {}

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
            "QScrollBar:vertical { background: transparent; width: 6px; margin: 0; }"
            "QScrollBar::handle:vertical { background: rgba(180,198,139,170); border-radius: 3px; min-height: 22px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )
        scroll_bar = self.history.verticalScrollBar()
        self._scroll_target = 0
        self._scroll_animation = QPropertyAnimation(scroll_bar, b"value", self)
        self._scroll_animation.setDuration(130)
        self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        root.addWidget(self.history, 1)

        self.history_navigation = HistoryNavigation()
        self.history_navigation.hide()
        self.history_navigation.latest_requested.connect(self._return_to_latest)
        root.addWidget(self.history_navigation)
        scroll_bar.valueChanged.connect(self._update_history_navigation)
        scroll_bar.rangeChanged.connect(self._update_history_navigation)

        self.composer = MessageComposer()
        self.input = self.composer.edit
        self.composer.configure(self._settings)
        self.composer.hide()
        self.input.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.input.setReadOnly(True)
        self.input.returnPressed.connect(self._submit)
        self.input.installEventFilter(self)
        self.history.viewport().installEventFilter(self)
        root.addWidget(self.composer)
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
    def is_connected(self) -> bool:
        return self._connected

    @property
    def backdrop_alpha(self) -> int:
        return round(255 * self._settings.backdrop_opacity / 100)

    def configure(self, settings: AppSettings) -> None:
        self._settings = settings
        self.composer.configure(settings)
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

    def merge_live_messages(self, messages: list[ChatMessage]) -> None:
        known_ids = {message.message_id for message in self.timeline.items}
        if not self.timeline.merge(messages):
            return
        expires = monotonic() + 1.4
        self._highlight_until.update(
            {
                message.message_id: expires
                for message in messages
                if message.message_id and message.message_id not in known_ids
            }
        )
        self._render_timeline()

    def clear_messages(self) -> None:
        self.timeline = ChatTimeline(limit=80)
        self._highlight_until.clear()
        self._stop_scroll_animation()
        self.history.clear()
        self._rendered_rows.clear()
        self._scroll_target = 0

    def _render_timeline(self, *, force_latest: bool = False) -> None:
        now = monotonic()
        self._highlight_until = {
            message_id: expires
            for message_id, expires in self._highlight_until.items()
            if expires > now
        }
        scroll_bar = self.history.verticalScrollBar()
        if hasattr(self, "_scroll_animation"):
            self._scroll_animation.stop()
        was_latest = scroll_bar.value() >= scroll_bar.maximum() - 2
        previous_scroll = scroll_bar.value()
        row_width = max(200, self.history.viewport().width())
        messages = self.timeline.items
        wanted = {message.message_id for message in messages}
        for message_id in tuple(self._rendered_rows):
            if message_id not in wanted:
                item, row, _ = self._rendered_rows.pop(message_id)
                self.history.removeItemWidget(item)
                self.history.takeItem(self.history.row(item))
                row.deleteLater()
        for index, message in enumerate(messages):
            signature = (
                message,
                self._settings.font_size,
                self._settings.text_opacity,
                row_width,
            )
            previous = self._rendered_rows.get(message.message_id)
            if previous is not None and previous[2] == signature:
                continue
            if previous is not None:
                item = previous[0]
                self.history.removeItemWidget(item)
            else:
                item = QListWidgetItem()
                self.history.insertItem(index, item)
            row = MessageRow(
                message,
                font_size=self._settings.font_size,
                text_opacity=self._settings.text_opacity,
                highlight=message.message_id in self._highlight_until,
            )
            row.setFixedWidth(row_width)
            row.layout().activate()
            height = row.layout().heightForWidth(row_width)
            item.setSizeHint(QSize(row_width, max(1, height) + 3))
            self.history.setItemWidget(item, row)
            self._rendered_rows[message.message_id] = (item, row, signature)
        if force_latest or not self._active or was_latest:

            def follow_latest() -> None:
                self.history.scrollToBottom()
                self._scroll_target = scroll_bar.maximum()

            follow_latest()
            QTimer.singleShot(0, follow_latest)
        else:

            def restore_scroll() -> None:
                scroll_bar.setValue(min(previous_scroll, scroll_bar.maximum()))
                self._scroll_target = scroll_bar.value()

            restore_scroll()
            QTimer.singleShot(0, restore_scroll)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        alpha = self.backdrop_alpha
        if alpha <= 0 and not self._editing:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(10, 17, 16, max(alpha, 155) if self._editing else alpha)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(self.rect().adjusted(3, 3, -3, -3), 5, 5)

    def _apply_font_size(self, font_size: int) -> None:
        self.input.setFont(_ui_font(font_size))
        input_height = QFontMetricsF(self.input.font()).height() + 8
        self.input.setFixedHeight(max(30, round(input_height)))
        if self.timeline.items:
            self._render_timeline()

    def _restore_topmost(self) -> None:
        if self.isVisible():
            ensure_window_topmost(int(self.winId()))

    def _set_scroll_position_visible(self, visible: bool) -> None:
        policy = (
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if visible
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.history.setVerticalScrollBarPolicy(policy)
        self._update_history_navigation()

    def _update_history_navigation(self, *_args) -> None:
        scroll = self.history.verticalScrollBar()
        browsing = self._active and scroll.value() < scroll.maximum() - 2
        self.history_navigation.setVisible(browsing)
        if browsing:
            item = self.history.itemAt(QPoint(1, 1))
            index = self.history.row(item) if item is not None else -1
            messages = self.timeline.items
            self.history_navigation.time.setText(
                message_time(messages[index].timestamp_us)
                if 0 <= index < len(messages)
                else ""
            )

    def _return_to_latest(self) -> None:
        self._stop_scroll_animation()
        self.history_navigation.hide()
        self.history.scrollToBottom()
        self._scroll_target = self.history.verticalScrollBar().maximum()
        self.input.setFocus(Qt.FocusReason.MouseFocusReason)

    def _stop_scroll_animation(self) -> None:
        self._scroll_animation.stop()
        self._scroll_target = self.history.verticalScrollBar().value()

    def _scroll_by_wheel_delta(self, delta: int) -> None:
        if not delta:
            return
        scroll_bar = self.history.verticalScrollBar()
        base = (
            self._scroll_target
            if self._scroll_animation.state() == QAbstractAnimation.State.Running
            else scroll_bar.value()
        )
        notch = max(32, min(72, round(self.history.viewport().height() * 0.22)))
        distance = round((delta / 120) * notch)
        if not distance:
            distance = 1 if delta > 0 else -1
        target = max(scroll_bar.minimum(), min(scroll_bar.maximum(), base - distance))
        self._scroll_target = target
        self._scroll_animation.stop()
        self._scroll_animation.setStartValue(scroll_bar.value())
        self._scroll_animation.setEndValue(target)
        self._scroll_animation.setDuration(
            max(90, min(180, 90 + abs(target - scroll_bar.value())))
        )
        self._scroll_animation.start()

    def handle_global_wheel(self, delta: int) -> bool:
        if not self._active or self._editing:
            return False
        self._scroll_by_wheel_delta(delta)
        return True

    def _set_interactive(self, interactive: bool) -> None:
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, not interactive
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, not interactive)
        if self.isVisible():
            set_window_click_through(int(self.winId()), not interactive)

    def _place_window(self) -> None:
        screen = next(
            (
                screen
                for screen in QGuiApplication.screens()
                if screen.name() == self._settings.screen_name
            ),
            self.screen(),
        )
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
            self._set_scroll_position_visible(False)
            self.interaction_changed.emit(False)
            self.hide()
            return
        self._active = False
        self._editing = False
        self._stop_scroll_animation()
        self._set_scroll_position_visible(False)
        self.interaction_changed.emit(False)
        self.editor.hide()
        self.resize_grip.hide()
        self.status.hide()
        self.composer.hide()
        self.composer.set_failed(False)
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
        previous_window = foreground_window()
        self._return_window_id = (
            previous_window if previous_window != int(self.winId()) else 0
        )
        self._active = True
        self._editing = False
        self._activation_guard = True
        self.composer.show()
        self.editor.hide()
        self.input.setEnabled(self._connected)
        self.input.setReadOnly(not self._connected)
        self.input.setPlaceholderText("")
        self.status.setVisible(not self._connected)
        self._place_window()
        self._stop_scroll_animation()
        self._set_scroll_position_visible(True)
        self._render_timeline(force_latest=True)
        self.resize_grip.hide()
        self.input.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._set_interactive(True)
        self.show()
        self._set_interactive(True)
        self._restore_topmost()
        self._focus_input()
        self.interaction_changed.emit(self._active)
        QTimer.singleShot(0, self._finish_activation)

    def _finish_activation(self) -> None:
        self._activation_guard = False
        if (
            self._native_windows
            and self._active
            and foreground_window() != int(self.winId())
        ):
            self.hide_overlay()

    def _focus_input(self) -> None:
        if not self._active:
            return
        self.raise_()
        self.activateWindow()
        self.input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        acquired = focus_window(int(self.winId()), int(self.winId()))
        if self._native_windows and not acquired:
            self.hide_overlay()
            self.activation_failed.emit(
                "无法激活输入。请确认当前程序没有使用更高的管理员权限。"
            )
            return
        prepare_input_method(int(self.winId()))

    def begin_edit_mode(self) -> None:
        self._active = False
        self._editing = True
        self._stop_scroll_animation()
        self._set_scroll_position_visible(False)
        self.interaction_changed.emit(False)
        self._edit_original = self.geometry()
        self._place_window()
        self.editor.show()
        self.editor.raise_()
        self.resize_grip.show()
        self.resize_grip.raise_()
        self.status.hide()
        self.composer.hide()
        self.composer.set_failed(False)
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

    def hide_overlay(self, *, restore_focus: bool = False) -> None:
        return_window_id = self._return_window_id
        self._return_window_id = 0
        self._active = False
        self._activation_guard = False
        self._stop_scroll_animation()
        self._set_scroll_position_visible(False)
        self.interaction_changed.emit(False)
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
        if restore_focus and return_window_id:
            restore_window(return_window_id, expected_foreground=int(self.winId()))

    def toggle_visibility(self) -> None:
        self._user_hidden = not self._user_hidden
        if self._user_hidden:
            self._active = False
            self._activation_guard = False
            self._stop_scroll_animation()
            self._set_scroll_position_visible(False)
            self.interaction_changed.emit(False)
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
        if self.input.is_composing or not self._active:
            return
        decision = self.intent.enter(
            hidden=False, target_active=False, draft=self.input.text()
        )
        text = decision.text
        should_send = decision.action is OverlayAction.SEND_AND_HIDE and bool(text)
        self.input.clear()
        self.hide_overlay(restore_focus=True)
        if should_send:
            self.send_requested.emit(text)

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self.input
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
        ):
            self.input.clear()
            self.hide_overlay(restore_focus=True)
            return True
        if (
            self._active
            and watched in {self.input, self.history.viewport()}
            and event.type() == QEvent.Type.Wheel
        ):
            delta = event.angleDelta().y()
            if delta:
                self._scroll_by_wheel_delta(delta)
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.input.clear()
            self.hide_overlay(restore_focus=True)
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
