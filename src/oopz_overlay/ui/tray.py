from pathlib import Path
from PySide6.QtCore import Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from ..i18n import tr


def app_icon() -> QIcon:
    """The same SVG exports supply native-size window, tray and exe icons."""
    assets = Path(__file__).resolve().parents[1] / 'assets'
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addFile(str(assets / f'icon-{size}.png'))
    return icon

class Tray(QSystemTrayIcon):
    toggle = Signal()
    settings_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(app_icon(), parent)
        self.menu = QMenu()
        self.menu.addAction(tr('settings'), self.settings_requested.emit)
        self.menu.addAction(tr('quit'), self.quit_requested.emit)
        self.setContextMenu(self.menu)
        self.activated.connect(self._activate)

    def _activate(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle.emit()

    def render(self, state):
        channel = '#' + state.settings.channel_name if state.settings.channel_id else tr('choose', hotkey=state.settings.hotkey)
        self.setToolTip(f"{tr('app')} · {channel} · {tr(state.status)}")
