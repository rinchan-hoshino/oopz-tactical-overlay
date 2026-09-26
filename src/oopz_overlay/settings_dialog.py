from __future__ import annotations
from dataclasses import replace
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QScrollArea,
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
from .preview import HudPreview
from .ui_common import APP_NAME, app_icon, _ui_font, _hotkey_from_event


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
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setMinimumSize(420, 440)
        self._base = current
        self._updating = True
        self._stacked = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(24, 18, 24, 16)
        row.setSpacing(12)
        mark = QLabel()
        mark.setPixmap(app_icon().pixmap(34, 34))
        row.addWidget(mark)
        title = QLabel(APP_NAME)
        title.setFont(_ui_font(17, QFont.Weight.DemiBold))
        row.addWidget(title)
        row.addStretch(1)
        self.connection_status = QLabel("未连接 Oopz")
        self.connection_status.setObjectName("connectionStatus")
        self.connection_status.setFont(_ui_font(9))
        row.addWidget(self.connection_status)
        root.addWidget(header)

        channel = QFrame()
        channel.setObjectName("channelBar")
        row = QHBoxLayout(channel)
        row.setContentsMargins(24, 10, 24, 10)
        row.setSpacing(10)
        self.server = QLabel(current.area_name or "Oopz")
        self.server.setTextFormat(Qt.TextFormat.PlainText)
        self.server.setMaximumWidth(190)
        row.addWidget(self.server)
        slash = QLabel("/")
        slash.setObjectName("muted")
        row.addWidget(slash)
        self.destination = QComboBox()
        self.destination.setAccessibleName("消息频道")
        self.destination.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.destination.setMinimumContentsLength(6)
        row.addWidget(self.destination, 1)
        self.sync_button = QPushButton("刷新")
        self.sync_button.setAccessibleName("刷新频道")
        row.addWidget(self.sync_button)
        root.addWidget(channel)
        self.state = QLabel()
        self.state.setObjectName("error")
        self.state.setTextFormat(Qt.TextFormat.PlainText)
        self.state.setWordWrap(True)
        self.state.setContentsMargins(24, 8, 24, 4)
        self.state.hide()
        root.addWidget(self.state)

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body_layout = QGridLayout(self.body)
        self.body_layout.setContentsMargins(24, 20, 24, 20)
        self.body_layout.setHorizontalSpacing(24)
        self.body_layout.setVerticalSpacing(22)
        self.body_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.preview_panel = QWidget()
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(10)
        preview_header = QHBoxLayout()
        heading = QLabel("预览")
        heading.setObjectName("section")
        preview_header.addWidget(heading)
        preview_header.addStretch(1)
        self.scene_buttons = QButtonGroup(self)
        self.preview = HudPreview(current)
        self.preview_frame = self.preview
        for light, label in ((False, "暗景"), (True, "亮景")):
            button = QPushButton(label)
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setChecked(light)
            self.scene_buttons.addButton(button)
            button.clicked.connect(
                lambda checked=False, light=light: self.preview.set_light_scene(light)
            )
            preview_header.addWidget(button)
        preview_layout.addLayout(preview_header)
        preview_layout.addWidget(self.preview)
        modes = QHBoxLayout()
        modes.setSpacing(3)
        self.preview_modes = QButtonGroup(self)
        self.mode_buttons = {}
        for mode, label in (
            ("passive", "平时"),
            ("input", "输入"),
            ("history", "回看"),
            ("failed", "发送失败"),
        ):
            button = QPushButton(label)
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setChecked(mode == "passive")
            self.preview_modes.addButton(button)
            self.mode_buttons[mode] = button
            button.clicked.connect(
                lambda checked=False, mode=mode: self.preview.set_mode(mode)
            )
            modes.addWidget(button)
        modes.addStretch(1)
        self.preview.mode_changed.connect(
            lambda mode: self.mode_buttons[mode].setChecked(True)
        )
        preview_layout.addLayout(modes)
        self.edit_button = QPushButton("调整位置与大小")
        preview_layout.addWidget(self.edit_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.controls_panel = QWidget()
        controls = QVBoxLayout(self.controls_panel)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(22)
        heading = QLabel("显示")
        heading.setObjectName("section")
        controls.addWidget(heading)
        self.font_size = QSpinBox()
        self.font_size.setRange(9, 20)
        self.font_size.setSuffix(" pt")
        self.font_size.setValue(current.font_size)
        self.font_size.setAccessibleName("文字大小")
        row = QHBoxLayout()
        row.addWidget(QLabel("文字大小"))
        row.addStretch(1)
        row.addWidget(self.font_size)
        controls.addLayout(row)
        self.text_opacity = QSlider(Qt.Orientation.Horizontal)
        self.text_opacity.setRange(20, 100)
        self.text_opacity.setValue(current.text_opacity)
        self.text_opacity_value = QLabel(f"{current.text_opacity}%")
        self.backdrop_opacity = QSlider(Qt.Orientation.Horizontal)
        self.backdrop_opacity.setRange(0, 85)
        self.backdrop_opacity.setValue(current.backdrop_opacity)
        self.backdrop_opacity_value = QLabel(f"{current.backdrop_opacity}%")
        for label, control, value in (
            ("文字不透明度", self.text_opacity, self.text_opacity_value),
            ("底色深度", self.backdrop_opacity, self.backdrop_opacity_value),
        ):
            group = QVBoxLayout()
            group.setSpacing(10)
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addStretch(1)
            value.setObjectName("muted")
            row.addWidget(value)
            group.addLayout(row)
            control.setAccessibleName(label)
            group.addWidget(control)
            controls.addLayout(group)
        self.always_visible = QCheckBox("连接后显示消息")
        self.always_visible.setChecked(current.always_visible)
        controls.addWidget(self.always_visible)
        controls.addStretch(1)
        self._arrange_body(760)
        scroll.setWidget(self.body)
        root.addWidget(scroll, 1)

        keys = QFrame()
        keys.setObjectName("shortcuts")
        row = QHBoxLayout(keys)
        row.setContentsMargins(24, 12, 24, 12)
        row.setSpacing(10)
        self.keys_label = QLabel("快捷键")
        self.keys_label.setObjectName("muted")
        row.addWidget(self.keys_label)
        row.addStretch(1)
        self.activation_hotkey = HotkeyRecorder(current.hotkey or "F8")
        self.visibility_hotkey = HotkeyRecorder(current.visibility_hotkey or "F9")
        for label, recorder in (
            ("输入消息", self.activation_hotkey),
            ("显示 / 隐藏", self.visibility_hotkey),
        ):
            row.addWidget(QLabel(label))
            recorder.setObjectName("hotkey")
            recorder.setAccessibleName(label + "快捷键")
            row.addWidget(recorder)
            recorder.recording_changed.connect(self.recording_changed.emit)
        root.addWidget(keys)
        footer = QWidget()
        row = QHBoxLayout(footer)
        row.setContentsMargins(24, 7, 24, 10)
        self.version = QLabel(f"v{__version__}")
        self.version.setObjectName("muted")
        self.version.setFont(_ui_font(9))
        self.update_status = QLabel("等待检查更新")
        self.update_status.setObjectName("muted")
        self.update_status.setFont(_ui_font(9))
        self.update_status.setWordWrap(True)
        row.addWidget(self.version)
        row.addStretch(1)
        row.addWidget(self.update_status)
        root.addWidget(footer)
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
        self._apply_theme()
        QApplication.instance().styleHints().colorSchemeChanged.connect(
            self._apply_theme
        )
        available = self.screen().availableGeometry()
        self.resize(min(760, available.width() - 40), min(640, available.height() - 50))

    def _apply_theme(self, scheme=None) -> None:
        scheme = (
            scheme
            if scheme is not None
            else QApplication.instance().styleHints().colorScheme()
        )
        dark = scheme == Qt.ColorScheme.Dark
        surface, raised, ink, muted, line, soft, accent = (
            (
                "#202221",
                "#2a2c2b",
                "#eeefeb",
                "#a3a8a0",
                "#383d36",
                "#2c312b",
                "#b4c68b",
            )
            if dark
            else (
                "#fbfbf9",
                "#ffffff",
                "#242924",
                "#686d66",
                "#e3e6df",
                "#f0f2ec",
                "#657247",
            )
        )
        self.setStyleSheet(f"""
            QDialog, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {surface}; color: {ink}; }}
            QLabel, QCheckBox {{ color: {ink}; background: transparent; }}
            QLabel#muted {{ color: {muted}; }}
            QLabel#section {{ font-weight: 600; }}
            QLabel#error {{ color: {"#dfba82" if dark else "#9b472f"}; }}
            QLabel#connectionStatus {{ color: {muted}; }}
            QLabel#connectionStatus[connected="true"] {{ color: {"#96b99e" if dark else "#4c7658"}; }}
            QFrame#channelBar {{ background: {raised}; border-top: 1px solid {line}; border-bottom: 1px solid {line}; }}
            QFrame#shortcuts {{ background: {raised}; border-top: 1px solid {line}; }}
            QPushButton, QComboBox, QSpinBox {{ color: {ink}; background: {raised}; border: 1px solid {line}; border-radius: 5px; padding: 5px 9px; min-height: 20px; }}
            QPushButton:hover, QComboBox:hover, QSpinBox:hover {{ border-color: {accent}; }}
            QPushButton:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {accent}; }}
            QPushButton:disabled {{ color: {muted}; }}
            QPushButton#segment {{ border: none; background: transparent; color: {muted}; padding: 3px 7px; }}
            QPushButton#segment:checked {{ color: {ink}; background: {soft}; }}
            QPushButton#hotkey {{ border-bottom: 2px solid {line}; min-width: 30px; background: {surface}; }}
            QComboBox QAbstractItemView {{ color: {ink}; background: {raised}; selection-background-color: {soft}; selection-color: {ink}; border: 1px solid {line}; }}
            QSlider::groove:horizontal {{ height: 4px; border-radius: 2px; background: {line}; }}
            QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {accent}; width: 14px; margin: -5px 0; border-radius: 7px; }}
            QScrollBar:vertical {{ background: transparent; width: 7px; }}
            QScrollBar::handle:vertical {{ background: {line}; border-radius: 3px; min-height: 24px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)

    def _arrange_body(self, width: int) -> None:
        stacked = width < 680
        if self._stacked == stacked:
            return
        self._stacked = stacked
        for widget in (self.preview_panel, self.controls_panel):
            self.body_layout.removeWidget(widget)
        self.body_layout.addWidget(self.preview_panel, 0, 0)
        self.body_layout.addWidget(
            self.controls_panel, 1 if stacked else 0, 0 if stacked else 1
        )
        self.body_layout.setColumnStretch(0, 1 if stacked else 3)
        self.body_layout.setColumnStretch(1, 0 if stacked else 2)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "body_layout"):
            self._arrange_body(self.width())
            self.keys_label.setVisible(self.width() >= 560)

    def _update_preview(self) -> None:
        destination = self.destination.currentData()
        self.preview.configure(
            replace(
                self._base,
                font_size=self.font_size.value(),
                text_opacity=self.text_opacity.value(),
                backdrop_opacity=self.backdrop_opacity.value(),
                channel_name=destination.channel_name
                if isinstance(destination, Destination)
                else "频道",
            )
        )

    def set_connection_status(self, text: str, connected: bool) -> None:
        self.connection_status.setText("已连接 Oopz" if connected else "未连接 Oopz")
        self.connection_status.setToolTip(text)
        self.connection_status.setProperty("connected", connected)
        self.connection_status.style().unpolish(self.connection_status)
        self.connection_status.style().polish(self.connection_status)
        self.state.setText("" if connected else text)
        self.state.setVisible(not connected and bool(text))

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
        self.sync_button.setText("读取中")
        self.state.clear()
        self.state.hide()
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
        self.sync_button.setText("刷新")
        self.state.clear()
        self.state.hide()
        self._updating = False
        self._update_preview()

    def show_error(self, message: str) -> None:
        self.sync_button.setEnabled(True)
        self.sync_button.setText("刷新")
        self.state.setText(message)
        self.state.setVisible(bool(message))

    def set_update_status(self, text: str) -> None:
        self.update_status.setText(
            "已是最新版" if text.startswith("已是最新版") else text
        )
        self.update_status.setToolTip(text)

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
