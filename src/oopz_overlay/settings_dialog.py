from __future__ import annotations
from dataclasses import replace
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QGridLayout,
)
from . import __version__
from .gateway import Destination, LoginResult
from .settings import AppSettings
from .win32_input import parse_hotkey
from .text_effect import TextOutlineEffect
from .ui_common import _ui_font, _hotkey_from_event


class HotkeyRecorder(QPushButton):
    hotkey_changed = Signal(str)
    recording_changed = Signal(bool)

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
        was_recording = self.is_recording
        self._value = value
        self.is_recording = False
        self._show_value()
        if was_recording:
            self.recording_changed.emit(False)

    def begin_recording(self) -> None:
        self.is_recording = True
        self.recording_changed.emit(True)
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
        if event.key() == Qt.Key.Key_Escape:
            self.is_recording = False
            self._show_value()
            self.recording_changed.emit(False)
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
        self.recording_changed.emit(False)
        self.hotkey_changed.emit(value)
        event.accept()

    def focusOutEvent(self, event) -> None:
        if self.is_recording:
            self.is_recording = False
            self._show_value()
            self.recording_changed.emit(False)
        super().focusOutEvent(event)


class SetupDialog(QDialog):
    session_requested = Signal()
    settings_changed = Signal(object)
    edit_requested = Signal()

    recording_changed = Signal(bool)

    def __init__(self, current: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFont(_ui_font(10))
        self.setWindowTitle("Oopz 文字上屏")
        self.setMinimumWidth(420)
        self.resize(480, 590)
        self._base = current
        self._updating = True
        self.setStyleSheet("""
            QDialog { background: palette(window); }
            QComboBox, QSpinBox, QPushButton { min-height: 24px; }
            QLabel#section { font-weight: 600; }
            QLabel#error { color: #c54838; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        def section(title: str):
            heading = QLabel(title)
            heading.setObjectName("section")
            root.addWidget(heading)

        section("频道")
        self.server = QLabel(current.area_name or "尚未读取 Oopz")
        self.server.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.server)
        self.destination = QComboBox()
        self.destination.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.destination.setMinimumContentsLength(12)
        root.addWidget(self.destination)
        connection_row = QHBoxLayout()
        self.state = QLabel(
            "手动选择 HUD 要读写的文字频道" if current.channel_id else "请选择文字频道"
        )
        self.state.setTextFormat(Qt.TextFormat.PlainText)
        self.state.setWordWrap(True)
        connection_row.addWidget(self.state, 1)
        self.sync_button = QPushButton("刷新频道")
        connection_row.addWidget(self.sync_button)
        root.addLayout(connection_row)
        self.connection_status = QLabel("未连接")
        self.connection_status.setTextFormat(Qt.TextFormat.PlainText)
        self.connection_status.setWordWrap(True)
        root.addWidget(self.connection_status)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)
        section("快捷键")
        keys = QGridLayout()
        keys.setHorizontalSpacing(20)
        self.activation_hotkey = HotkeyRecorder(current.hotkey or "F8")
        self.visibility_hotkey = HotkeyRecorder(current.visibility_hotkey or "F9")
        for row, (label, recorder) in enumerate(
            [
                ("输入消息", self.activation_hotkey),
                ("显示 / 隐藏", self.visibility_hotkey),
            ]
        ):
            keys.addWidget(QLabel(label), row, 0)
            keys.addWidget(recorder, row, 1)
            recorder.recording_changed.connect(self.recording_changed.emit)
        keys.setColumnStretch(1, 1)
        root.addLayout(keys)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)
        section("外观")
        appearance = QGridLayout()
        appearance.setHorizontalSpacing(14)
        self.font_size = QSpinBox()
        self.font_size.setRange(9, 20)
        self.font_size.setSuffix(" pt")
        self.font_size.setValue(current.font_size)
        appearance.addWidget(QLabel("文字大小"), 0, 0)
        appearance.addWidget(self.font_size, 0, 1, 1, 2)
        self.text_opacity = QSlider(Qt.Orientation.Horizontal)
        self.text_opacity.setRange(20, 100)
        self.text_opacity.setValue(current.text_opacity)
        self.text_opacity_value = QLabel(f"{current.text_opacity}%")
        self.backdrop_opacity = QSlider(Qt.Orientation.Horizontal)
        self.backdrop_opacity.setRange(0, 85)
        self.backdrop_opacity.setValue(current.backdrop_opacity)
        self.backdrop_opacity_value = QLabel(f"{current.backdrop_opacity}%")
        for row, (label, control, value) in enumerate(
            [
                ("文字透明度", self.text_opacity, self.text_opacity_value),
                ("背景遮罩", self.backdrop_opacity, self.backdrop_opacity_value),
            ],
            1,
        ):
            appearance.addWidget(QLabel(label), row, 0)
            appearance.addWidget(control, row, 1)
            value.setMinimumWidth(40)
            value.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            appearance.addWidget(value, row, 2)
        appearance.setColumnStretch(1, 1)
        root.addLayout(appearance)
        self.preview_frame = QFrame()
        preview_layout = QVBoxLayout(self.preview_frame)
        preview_layout.setContentsMargins(12, 7, 12, 7)
        self.preview = QLabel("风屿  二楼窗口有人\n你  收到，我绕右侧")
        self.preview.setTextFormat(Qt.TextFormat.PlainText)
        self.preview.setMinimumHeight(70)
        self.preview.setWordWrap(True)
        self.preview.setGraphicsEffect(TextOutlineEffect(self.preview))
        preview_layout.addWidget(self.preview)
        root.addWidget(self.preview_frame)
        self.always_visible = QCheckBox("连接后显示 HUD")
        self.always_visible.setChecked(current.always_visible)
        self.edit_button = QPushButton("调整位置与大小…")
        row = QHBoxLayout()
        row.addWidget(self.always_visible)
        row.addStretch(1)
        row.addWidget(self.edit_button)
        root.addLayout(row)
        root.addStretch(1)
        footer = QHBoxLayout()
        self.version = QLabel(f"v{__version__}")
        self.update_status = QLabel("等待检查更新")
        self.update_status.setObjectName("updateStatus")
        self.update_status.setWordWrap(True)
        footer.addWidget(self.version)
        footer.addStretch(1)
        footer.addWidget(self.update_status)
        root.addLayout(footer)
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
        self._update_preview()

    def _update_preview(self) -> None:
        self.preview.setFont(_ui_font(self.font_size.value()))
        self.preview_frame.setStyleSheet(
            f"background: rgba(0, 0, 0, {round(self.backdrop_opacity.value() * 2.55)});"
        )
        self.preview.setStyleSheet("background: transparent; color: white;")
        self.preview.graphicsEffect().set_opacity(self.text_opacity.value() / 100)

    def set_connection_status(self, text: str, connected: bool) -> None:
        self.connection_status.setText("已连接 · " + text if connected else text)

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
        self.sync_button.setText("刷新频道")
        self.state.setText("手动选择 HUD 要读写的文字频道")
        self._updating = False

    def show_error(self, message: str) -> None:
        self.sync_button.setEnabled(True)
        self.sync_button.setText("刷新频道")
        self.state.setText(message)

    def set_update_status(self, text: str) -> None:
        self.update_status.setText(text)

    def sync_settings(self, settings: AppSettings) -> None:
        self._base = settings
        self._updating = True
        self.activation_hotkey.set_hotkey(settings.hotkey)
        self.visibility_hotkey.set_hotkey(settings.visibility_hotkey)
        self.font_size.setValue(settings.font_size)
        self.text_opacity.setValue(settings.text_opacity)
        self.backdrop_opacity.setValue(settings.backdrop_opacity)
        self.always_visible.setChecked(settings.always_visible)
        self._updating = False
        self._update_preview()

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
        self._update_preview()
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
