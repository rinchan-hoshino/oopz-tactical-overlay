from dataclasses import replace
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QDialog, QFormLayout, QVBoxLayout, QLabel, QPushButton, QSlider, QSpinBox, QComboBox
from .. import __version__
from ..adapters.win32 import parse_hotkey, system_sounds, play_sound
from ..i18n import tr

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

class SettingsWindow(QDialog):
    changed = Signal(object)
    recording = Signal(bool)
    sound_preview = Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle(tr('settings'))
        self.setFixedWidth(360)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 16)
        outer.setSpacing(16)
        form = QFormLayout()
        form.setSpacing(14)
        outer.addLayout(form)
        self.hotkey = HotkeyButton(settings.hotkey, self)
        self.visibility_hotkey = HotkeyButton(settings.visibility_hotkey, self)
        for key, button in [('hotkey', self.hotkey), ('visibility_hotkey', self.visibility_hotkey)]:
            form.addRow(tr('input_hotkey' if key == 'hotkey' else key), button)
            button.recording.connect(self.recording.emit)
            button.recorded.connect(lambda value, k=key: self.change(k, value))
        self.strength = QSlider(Qt.Orientation.Horizontal, self)
        self.strength.setRange(0, 100)
        self.strength.setValue(settings.strength)
        self.strength.setAccessibleName(tr('strength'))
        form.addRow(tr('strength'), self.strength)
        self.strength.valueChanged.connect(lambda value: self.change('strength', value))
        self.font_size = QSpinBox(self)
        self.font_size.setRange(9, 20)
        self.font_size.setValue(settings.font_size)
        form.addRow(tr('font_size'), self.font_size)
        self.font_size.valueChanged.connect(lambda value: self.change('font_size', value))
        self.sound = QComboBox(self)
        self.sound.addItem(tr('off'), '')
        available = system_sounds()
        choices = available[:5]
        if settings.notification_sound and all((key != settings.notification_sound for _, key in choices)):
            choices.append(next(((label, key) for label, key in available if key == settings.notification_sound), (settings.notification_sound, settings.notification_sound)))
        for label, key in choices:
            self.sound.addItem(label, key)
        self.sound.setCurrentIndex(max(0, self.sound.findData(settings.notification_sound)))
        form.addRow(tr('sound'), self.sound)
        self.sound.currentIndexChanged.connect(self.preview_sound)
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
        self.changed.emit(self.settings)

    def preview_sound(self):
        key = self.sound.currentData()
        self.change('notification_sound', key)
        play_sound(key, preview=True)

    def sync(self, settings):
        self.settings = settings
        for widget, value in ((self.hotkey, settings.hotkey), (self.visibility_hotkey, settings.visibility_hotkey)):
            widget.value = value
            if not widget.listening:
                widget.setText(value)
        for widget, value in ((self.strength, settings.strength), (self.font_size, settings.font_size)):
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)

    def set_update_status(self, text):
        self.footer.setText(f'{__version__} · {text}')

    def closeEvent(self, event):
        self.hotkey.finish()
        self.visibility_hotkey.finish()
        super().closeEvent(event)
