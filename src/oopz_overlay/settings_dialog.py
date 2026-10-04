from __future__ import annotations
from .i18n import tr
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
from .sounds import play_sound, system_sounds
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
        self.setText(tr("请按下按键…"))
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
        self.setWindowTitle(tr(APP_NAME))
        self.setWindowIcon(app_icon())
        self.setMinimumSize(340, 440)
        self._base = current
        self._updating = True
        self._stacked = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(16, 14, 16, 12)
        row.setSpacing(12)
        mark = QLabel()
        mark.setPixmap(app_icon().pixmap(26, 26))
        row.addWidget(mark)
        identity = QVBoxLayout()
        identity.setSpacing(3)
        title = QLabel(tr(APP_NAME))
        title.setFont(_ui_font(17, QFont.Weight.DemiBold))
        identity.addWidget(title)
        self.connection_status = QLabel(tr("未连接 Oopz"))
        self.connection_status.setObjectName("connectionStatus")
        self.connection_status.setFont(_ui_font(9))
        identity.addWidget(self.connection_status)
        row.addLayout(identity, 1)
        root.addWidget(header)

        channel = QFrame()
        channel.setObjectName("channelBar")
        channel_layout = QVBoxLayout(channel)
        channel_layout.setContentsMargins(16, 10, 16, 10)
        channel_layout.setSpacing(8)
        self.server = QLabel(current.area_name or "Oopz")
        self.server.setTextFormat(Qt.TextFormat.PlainText)
        self.server.setWordWrap(True)
        channel_layout.addWidget(self.server)
        row = QHBoxLayout()
        row.setSpacing(8)
        channel_layout.addLayout(row)
        self.destination = QComboBox()
        self.destination.setAccessibleName(tr("消息频道"))
        self.destination.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.destination.setMinimumContentsLength(6)
        row.addWidget(self.destination, 1)
        self.sync_button = QPushButton(tr("刷新"))
        self.sync_button.setAccessibleName(tr("刷新频道"))
        row.addWidget(self.sync_button)
        root.addWidget(channel)
        self.state = QLabel()
        self.state.setObjectName("error")
        self.state.setTextFormat(Qt.TextFormat.PlainText)
        self.state.setWordWrap(True)
        self.state.setContentsMargins(16, 8, 16, 4)
        self.state.hide()
        root.addWidget(self.state)

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body_layout = QGridLayout(self.body)
        self.body_layout.setContentsMargins(16, 16, 16, 16)
        self.body_layout.setHorizontalSpacing(24)
        self.body_layout.setVerticalSpacing(22)
        self.body_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.preview_panel = QWidget()
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(10)
        preview_header = QHBoxLayout()
        heading = QLabel(tr("预览"))
        heading.setObjectName("section")
        preview_header.addWidget(heading)
        preview_header.addStretch(1)
        self.scene_buttons = QButtonGroup(self)
        self.preview = HudPreview(current)
        self.preview_frame = self.preview
        for light, label in ((False, tr("暗景")), (True, tr("亮景"))):
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
            ("passive", tr("平时")),
            ("input", tr("输入")),
            ("history", tr("回看")),
            ("failed", tr("发送失败")),
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
        self.edit_button = QPushButton(tr("调整位置与大小"))
        preview_layout.addWidget(self.edit_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.controls_panel = QWidget()
        controls = QVBoxLayout(self.controls_panel)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(22)
        heading = QLabel(tr("显示"))
        heading.setObjectName("section")
        controls.addWidget(heading)
        self.font_size = QSpinBox()
        self.font_size.setRange(9, 20)
        self.font_size.setSuffix(" pt")
        self.font_size.setValue(current.font_size)
        self.font_size.setAccessibleName(tr("文字大小"))
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("文字大小")))
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
            (tr("文字不透明度"), self.text_opacity, self.text_opacity_value),
            (tr("底色深度"), self.backdrop_opacity, self.backdrop_opacity_value),
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
        self.always_visible = QCheckBox(tr("连接后显示消息"))
        self.always_visible.setChecked(current.always_visible)
        controls.addWidget(self.always_visible)
        group = QVBoxLayout()
        group.setSpacing(10)
        group.addWidget(QLabel(tr("消息提示音")))
        row = QHBoxLayout()
        self.notification_sound = QComboBox()
        self.notification_sound.setAccessibleName(tr("消息提示音"))
        self.notification_sound.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.notification_sound.setMinimumContentsLength(8)
        self.notification_sound.addItem(tr("关闭"), "")
        for label, key in system_sounds():
            self.notification_sound.addItem(label, key)
        self.sound_preview = QPushButton(tr("试听"))
        self.sound_preview.setAccessibleName(tr("试听消息提示音"))
        self._select_sound(current.notification_sound)
        row.addWidget(self.notification_sound, 1)
        row.addWidget(self.sound_preview)
        group.addLayout(row)
        controls.addLayout(group)
        controls.addStretch(1)
        self._arrange_body(340)
        scroll.setWidget(self.body)
        root.addWidget(scroll, 1)

        keys = QFrame()
        keys.setObjectName("shortcuts")
        row = QGridLayout(keys)
        row.setContentsMargins(16, 10, 16, 10)
        row.setHorizontalSpacing(10)
        self.activation_hotkey = HotkeyRecorder(current.hotkey or "F8")
        self.visibility_hotkey = HotkeyRecorder(current.visibility_hotkey or "F9")
        for column, (label, recorder) in enumerate((
            (tr("输入消息"), self.activation_hotkey),
            (tr("显示 / 隐藏"), self.visibility_hotkey),
        )):
            row.addWidget(QLabel(label), 0, column)
            recorder.setObjectName("hotkey")
            recorder.setAccessibleName(label + tr("快捷键"))
            row.addWidget(recorder, 1, column)
            recorder.recording_changed.connect(self.recording_changed.emit)
        root.addWidget(keys)
        footer = QWidget()
        row = QHBoxLayout(footer)
        row.setContentsMargins(16, 7, 16, 10)
        self.version = QLabel(f"v{__version__}")
        self.version.setObjectName("muted")
        self.version.setFont(_ui_font(9))
        self.update_status = QLabel(tr("等待检查更新"))
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
        self.notification_sound.currentIndexChanged.connect(self._sound_changed)
        self.sound_preview.clicked.connect(self._preview_sound)
        self._populate_current_destination(current)
        self._updating = False
        self._update_preview()
        self._apply_theme()
        QApplication.instance().styleHints().colorSchemeChanged.connect(
            self._apply_theme
        )
        available = self.screen().availableGeometry()
        self.resize(min(360, available.width() - 40), min(900, available.height() - 50))

    def _apply_theme(self, scheme=None) -> None:
        scheme = (
            scheme
            if scheme is not None
            else QApplication.instance().styleHints().colorScheme()
        )
        dark = scheme == Qt.ColorScheme.Dark
        surface, raised, ink, muted, line, soft, accent = (
            (
                "#2c2c2e",
                "#2a2c2b",
                "#f5f5f7",
                "#a3a8a0",
                "#383d36",
                "#2c312b",
                "#8accff",
            )
            if dark
            else (
                "#ffffff",
                "#ffffff",
                "#1d1d1f",
                "#686d66",
                "#d2d2d7",
                "#f5f5f7",
                "#0071e3",
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
        if self._stacked:
            return
        self._stacked = True
        self.body_layout.addWidget(self.preview_panel, 0, 0)
        self.body_layout.addWidget(self.controls_panel, 1, 0)
        self.body_layout.setColumnStretch(0, 1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "body_layout"):
            self._arrange_body(self.width())

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
                else tr("频道"),
            )
        )

    def set_connection_status(self, text: str, connected: bool) -> None:
        self.connection_status.setText(tr("已连接 Oopz") if connected else tr("未连接 Oopz"))
        self.connection_status.setToolTip(text)
        self.connection_status.setProperty("connected", connected)
        self.connection_status.style().unpolish(self.connection_status)
        self.connection_status.style().polish(self.connection_status)
        self.state.setText("" if connected else tr(text))
        self.state.setVisible(not connected and bool(text))

    def _populate_current_destination(self, current: AppSettings) -> None:
        self.destination.clear()
        if current.area_id:
            self.server.setText(current.area_name or tr("上次选择的服务器"))
        if current.area_id and current.channel_id:
            destination = Destination(
                current.area_id,
                current.area_name or tr("当前服务器"),
                current.channel_id,
                current.channel_name or tr("当前频道"),
            )
            self.destination.addItem(destination.label, destination)
        else:
            self.destination.addItem(tr("正在读取频道…"), None)

    def _read_session(self) -> None:
        self.sync_button.setEnabled(False)
        self.sync_button.setText(tr("读取中"))
        self.state.clear()
        self.state.hide()
        self.session_requested.emit()

    def apply_login_result(self, result: LoginResult) -> None:
        self._updating = True
        self._base = result.settings
        current_key = (result.settings.area_id, result.settings.channel_id)
        self.server.setText(result.current_area_name or tr("未检测到当前语音服务器"))
        self.destination.clear()
        self.destination.addItem(tr("请选择文字频道"), None)
        selected = 0
        for destination in result.destinations:
            self.destination.addItem(destination.label, destination)
            if (destination.area_id, destination.channel_id) == current_key:
                selected = self.destination.count() - 1
        if not result.destinations:
            self.destination.setItemText(0, tr("请先加入 Oopz 语音服务器"))
        self.destination.setCurrentIndex(selected)
        self.sync_button.setEnabled(True)
        self.sync_button.setText(tr("刷新"))
        self.state.clear()
        self.state.hide()
        self._updating = False
        self._update_preview()

    def show_error(self, message: str) -> None:
        self.sync_button.setEnabled(True)
        self.sync_button.setText(tr("刷新"))
        self.state.setText(tr(message))
        self.state.setVisible(bool(message))

    def set_update_status(self, text: str) -> None:
        self.update_status.setText(
            tr("已是最新版") if text.startswith("已是最新版") else tr(text)
        )
        self.update_status.setToolTip(tr(text))

    def sync_settings(self, settings: AppSettings) -> None:
        self._base = settings
        self._updating = True
        self.activation_hotkey.set_hotkey(settings.hotkey)
        self.visibility_hotkey.set_hotkey(settings.visibility_hotkey)
        self.font_size.setValue(settings.font_size)
        self.text_opacity.setValue(settings.text_opacity)
        self.backdrop_opacity.setValue(settings.backdrop_opacity)
        self.always_visible.setChecked(settings.always_visible)
        self._select_sound(settings.notification_sound)
        self._updating = False
        self._update_preview()

    def _select_sound(self, key: str) -> None:
        index = self.notification_sound.findData(key)
        if index < 0:
            self.notification_sound.addItem(tr("所选声音不可用"), key)
            index = self.notification_sound.count() - 1
            self.notification_sound.model().item(index).setEnabled(False)
        self.notification_sound.setCurrentIndex(index)
        self._update_sound_preview()

    def _update_sound_preview(self) -> None:
        index = self.notification_sound.currentIndex()
        self.sound_preview.setEnabled(
            bool(self.notification_sound.currentData())
            and self.notification_sound.model().item(index).isEnabled()
        )

    def _sound_changed(self) -> None:
        self._update_sound_preview()
        self._emit_current()

    def _preview_sound(self) -> None:
        if not play_sound(self.notification_sound.currentData(), preview=True):
            self.show_error(tr("这个声音暂时无法播放，请选择其他提示音。"))

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
            "notification_sound": self.notification_sound.currentData(),
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
