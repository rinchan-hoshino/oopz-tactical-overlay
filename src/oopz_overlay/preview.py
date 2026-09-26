from __future__ import annotations

from dataclasses import replace
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPolygonF
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from .chat import ChatMessage
from .message_widgets import HistoryNavigation, MessageComposer, MessageRow
from .settings import AppSettings


class HudPreview(QWidget):
    mode_changed = Signal(str)

    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(264)
        self.setMinimumWidth(260)
        self.setAccessibleName("游戏消息预览")
        self.settings = settings
        self.mode = "passive"
        self.light_scene = True
        self._messages = [
            ChatMessage("preview-1", 0, "a", "风屿", "二楼窗口有人", False),
            ChatMessage("preview-2", 0, "self", "你", "收到，我绕右侧", True),
            ChatMessage("preview-3", 0, "b", "小满", "我看着楼梯，你们先走", False),
        ]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 18)
        layout.addStretch(1)
        self.hud = QFrame()
        self.hud.setObjectName("previewHud")
        content = QVBoxLayout(self.hud)
        content.setContentsMargins(9, 8, 9, 8)
        content.setSpacing(3)
        self.rows = QVBoxLayout()
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(3)
        content.addLayout(self.rows)
        self.history_navigation = HistoryNavigation()
        self.history_navigation.time.setText("21:34")
        self.history_navigation.latest_requested.connect(lambda: self.set_mode("input"))
        content.addWidget(self.history_navigation)
        self.composer = MessageComposer()
        self.composer.edit.returnPressed.connect(self._submit)
        content.addWidget(self.composer)
        self.failure = self.composer.failure
        layout.addWidget(self.hud)
        self.configure(settings)
        self.set_mode("passive")

    def configure(self, settings: AppSettings) -> None:
        self.settings = settings
        self.composer.configure(settings)
        self.hud.setStyleSheet(
            "QFrame#previewHud { border: none; border-radius: 5px;"
            f"background-color: rgba(10,17,16,{round(settings.backdrop_opacity * 2.55)}); }}"
        )
        self._render_rows()

    def set_light_scene(self, light: bool) -> None:
        self.light_scene = light
        self.update()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.history_navigation.setVisible(mode == "history")
        self.composer.setVisible(mode in {"input", "history", "failed"})
        self.composer.set_failed(mode == "failed")
        if mode == "failed" and not self.composer.edit.text():
            self.composer.edit.setText("等我一下，马上到")
        self._render_rows()
        self.mode_changed.emit(mode)

    def _render_rows(self) -> None:
        while self.rows.count():
            row = self.rows.takeAt(0).widget()
            row.hide()
            row.deleteLater()
        messages = self._messages
        if self.mode == "history":
            messages = [
                replace(m, text=t)
                for m, t in zip(messages, ["到一楼了", "我在楼梯口", "门已经开了"])
            ]
        for message in messages:
            self.rows.addWidget(
                MessageRow(message, self.settings.font_size, self.settings.text_opacity)
            )

    def _submit(self) -> None:
        edit = self.composer.edit
        if edit.is_composing or self.mode == "failed" or not edit.text().strip():
            return
        self._messages = self._messages[-2:] + [
            ChatMessage("preview-send", 0, "self", "你", edit.text().strip(), True)
        ]
        edit.clear()
        self.set_mode("passive")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 8, 8)
        painter.setClipPath(clip)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        colors = (
            ("#b9c8bf", "#d8d9bc", "#96ac95")
            if self.light_scene
            else ("#152326", "#293a36", "#5a6049")
        )
        for stop, color in zip((0, 0.55, 1), colors):
            gradient.setColorAt(stop, QColor(color))
        painter.fillRect(self.rect(), gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(48, 72, 57, 50))
        w, h = self.width(), self.height()
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(0, h * 0.65),
                    QPointF(w * 0.2, h * 0.25),
                    QPointF(w * 0.38, h * 0.56),
                    QPointF(w * 0.62, h * 0.18),
                    QPointF(w, h * 0.7),
                ]
            )
        )
        shade = QLinearGradient(0, h * 0.5, 0, h)
        shade.setColorAt(0, QColor(16, 29, 28, 0))
        shade.setColorAt(1, QColor(16, 29, 28, 110))
        painter.fillRect(self.rect(), shade)
        painter.end()
