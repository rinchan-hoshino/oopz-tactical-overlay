from dataclasses import replace
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QDialog, QFormLayout, QVBoxLayout, QLabel, QPushButton, QSlider, QSpinBox, QComboBox, QWidget, QHBoxLayout, QCheckBox
from .. import __version__
from ..adapters.win32 import parse_hotkey, system_sounds, play_sound
from ..i18n import tr
from .hud import Hud, sample_timeline
from ..core.state import AppState
from PySide6.QtGui import QPainter, QColor

class HotkeyButton(QPushButton):
    recorded = Signal(str)
    recording = Signal(bool)

    def __init__(self, value, parent):
        super().__init__(value, parent)
        self.value = value
        self.listening = False
        self.clicked.connect(self.begin)

    def begin(self):
        self.listening = True
        self.setText(tr('record'))
        self.recording.emit(True)

    def finish(self):
        if self.listening:
            self.listening = False
            self.setText(self.value)
            self.recording.emit(False)

    def focusOutEvent(self, event):
        self.finish()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if not self.listening:
            return super().keyPressEvent(event)
        if event.key() == Qt.Key.Key_Escape:
            self.finish()
            return
        value = QKeySequence(event.keyCombination()).toString(QKeySequence.SequenceFormat.PortableText).replace('Meta+', 'Win+')
        try:
            parse_hotkey(value)
        except ValueError:
            return
        self.value = value
        self.finish()
        self.recorded.emit(value)

class Preview(QWidget):
    def __init__(self, settings, parent):
        super().__init__(parent)
        self.scene = 'white'
        self.setFixedHeight(168)
        self.setAccessibleName(tr('preview'))
        self.hud = Hud(self)
        self.hud.setMinimumSize(0, 0)
        self.hud.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.timeline = sample_timeline()
        self.configure(settings)

    def configure(self, settings):
        self.hud.render(AppState(settings=replace(settings, always_visible=True), status=''), self.timeline, ())
        self.hud.hint.hide()

    def set_scene(self, scene):
        self.scene = scene
        self.update()

    def resizeEvent(self, event):
        self.hud.setGeometry(self.rect())
        super().resizeEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#ffffff' if self.scene == 'white' else '#000000'))
        if self.scene == 'mixed':
            for x in range(0, self.width(), 32):
                p.fillRect(x, 0, 16, self.height(), QColor('#d6d0ab'))
                p.fillRect(x + 16, 0, 16, self.height(), QColor('#547368'))


class SettingsWindow(QDialog):
    changed = Signal(object)
    recording = Signal(bool)
    edit_requested = Signal()

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle(tr('settings_title'))
        self.setFixedWidth(440)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(12)
        heading = QHBoxLayout()
        heading.addWidget(QLabel(tr('preview'), self))
        heading.addStretch()
        self.scene = QComboBox(self)
        for key in ('white', 'black', 'mixed'):
            self.scene.addItem(tr(key + '_scene'), key)
        self.scene.setAccessibleName(tr('preview_background'))
        heading.addWidget(self.scene)
        outer.addLayout(heading)
        self.preview = Preview(settings, self)
        outer.addWidget(self.preview)
        self.scene.currentIndexChanged.connect(lambda: self.preview.set_scene(self.scene.currentData()))
        self.edit_button = QPushButton(tr('adjust'), self)
        self.edit_button.clicked.connect(self.edit_requested.emit)
        outer.addWidget(self.edit_button)
        form = QFormLayout()
        form.setSpacing(12)
        outer.addLayout(form)
        self.font_size = QSpinBox(self)
        self.font_size.setRange(9, 20)
        self.font_size.setSuffix(' pt')
        self.font_size.setValue(settings.font_size)
        self.font_size.setAccessibleName(tr('font_size'))
        form.addRow(tr('font_size'), self.font_size)
        self.font_size.valueChanged.connect(lambda value: self.change('font_size', value))
        self.percentages = {}
        for key, maximum in (('text_opacity', 100), ('backdrop_opacity', 85)):
            row = QHBoxLayout()
            slider = QSlider(Qt.Orientation.Horizontal, self)
            slider.setRange(20 if key == 'text_opacity' else 0, maximum)
            slider.setValue(getattr(settings, key))
            slider.setAccessibleName(tr(key))
            if key == 'backdrop_opacity':
                slider.setToolTip(tr('backdrop_hint'))
            setattr(self, key, slider)
            row.addWidget(slider)
            label = QLabel(f'{slider.value()}%', self)
            label.setMinimumWidth(38)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(label)
            self.percentages[key] = label
            slider.valueChanged.connect(lambda value, k=key: self.change(k, value))
            form.addRow(tr(key), row)
        self.always_visible = QCheckBox(tr('always_visible'), self)
        self.always_visible.setToolTip(tr('persistence_hint'))
        self.always_visible.setChecked(settings.always_visible)
        self.always_visible.toggled.connect(lambda value: self.change('always_visible', value))
        form.addRow('', self.always_visible)
        self.hotkey = HotkeyButton(settings.hotkey, self)
        self.visibility_hotkey = HotkeyButton(settings.visibility_hotkey, self)
        for key, button in [('hotkey', self.hotkey), ('visibility_hotkey', self.visibility_hotkey)]:
            label = tr('input_hotkey' if key == 'hotkey' else key)
            button.setAccessibleName(label)
            form.addRow(label, button)
            button.recording.connect(self.recording.emit)
            button.recorded.connect(lambda value, k=key: self.change(k, value))
        self.sound = QComboBox(self)
        self.sound.setAccessibleName(tr('sound'))
        self.sound.setMaxVisibleItems(12)
        self.sound.addItem(tr('off'), '')
        available = system_sounds()
        for label, key in available:
            self.sound.addItem(label, key)
        if settings.notification_sound and self.sound.findData(settings.notification_sound) < 0:
            self.sound.addItem(tr('sound_unavailable') + ': ' + settings.notification_sound, settings.notification_sound)
        self._available_sounds = {key for _, key in available}
        self.sound.setCurrentIndex(max(0, self.sound.findData(settings.notification_sound)))
        self.listen = QPushButton(tr('sound_preview'), self)
        self.listen.setEnabled(settings.notification_sound in self._available_sounds)
        self.listen.clicked.connect(self.preview_sound)
        sound_row = QHBoxLayout()
        sound_row.addWidget(self.sound, 1)
        sound_row.addWidget(self.listen)
        form.addRow(tr('sound'), sound_row)
        self.sound.currentIndexChanged.connect(lambda: self.change('notification_sound', self.sound.currentData()))
        self.sound_error = QLabel(tr('sound_failed'), self)
        self.sound_error.setWordWrap(True)
        self.sound_error.hide()
        outer.addWidget(self.sound_error)
        self.footer = QLabel(self)
        self.footer.setWordWrap(True)
        f = self.footer.font()
        f.setPointSize(max(8, f.pointSize() - 1))
        self.footer.setFont(f)
        outer.addWidget(self.footer)
        self.set_update_status(tr('checking'))
        self.adjustSize()

    def change(self, key, value):
        self.settings = replace(self.settings, **{key: value})
        self.sync(self.settings)
        self.changed.emit(self.settings)

    def preview_sound(self):
        self.sound_error.setVisible(not play_sound(self.sound.currentData(), preview=True))

    def sync(self, settings):
        self.settings = settings
        for widget, value in ((self.hotkey, settings.hotkey), (self.visibility_hotkey, settings.visibility_hotkey)):
            widget.value = value
            if not widget.listening:
                widget.setText(value)
        for key in ('text_opacity', 'backdrop_opacity', 'font_size'):
            widget = getattr(self, key)
            widget.blockSignals(True)
            widget.setValue(getattr(settings, key))
            widget.blockSignals(False)
        for key, label in self.percentages.items():
            label.setText(f'{getattr(settings, key)}%')
        self.always_visible.blockSignals(True)
        self.always_visible.setChecked(settings.always_visible)
        self.always_visible.blockSignals(False)
        self.sound.blockSignals(True)
        self.sound.setCurrentIndex(max(0, self.sound.findData(settings.notification_sound)))
        self.sound.blockSignals(False)
        self.listen.setEnabled(settings.notification_sound in self._available_sounds)
        self.sound_error.hide()
        self.preview.configure(settings)

    def set_update_status(self, text):
        self.footer.setText(f'{__version__} · {text}')

    def closeEvent(self, event):
        self.hotkey.finish()
        self.visibility_hotkey.finish()
        super().closeEvent(event)
