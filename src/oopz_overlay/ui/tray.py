from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPainterPath, QPen
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from ..i18n import tr
ACCENT = '#657247'

def app_icon() -> QIcon:
    """One vector drawing for the window, tray and packaged application."""
    pixmap = QPixmap(256, 256)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(ACCENT))
    painter.drawRoundedRect(8, 8, 240, 240, 58, 58)
    paper = QPainterPath()
    paper.moveTo(69, 49)
    paper.lineTo(147, 49)
    paper.lineTo(189, 91)
    paper.lineTo(189, 207)
    paper.lineTo(69, 207)
    paper.closeSubpath()
    painter.setBrush(QColor('#f4f5e9'))
    painter.drawPath(paper)
    fold = QPainterPath()
    fold.moveTo(147, 49)
    fold.lineTo(147, 91)
    fold.lineTo(189, 91)
    fold.closeSubpath()
    painter.setBrush(QColor('#cbd3b4'))
    painter.drawPath(fold)
    painter.setPen(QPen(QColor(ACCENT), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(93, 127, 163, 127)
    painter.drawLine(93, 154, 145, 154)
    painter.end()
    return QIcon(pixmap)

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
