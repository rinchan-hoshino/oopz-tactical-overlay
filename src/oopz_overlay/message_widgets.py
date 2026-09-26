from __future__ import annotations

from datetime import UTC, datetime
from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QTextLayout,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from .chat import ChatMessage
from .text_effect import TextOutlineEffect
from .ui_common import ACCENT_HOT, TEXT, _ui_font, _with_opacity


def message_time(timestamp_us: int) -> str:
    if not timestamp_us:
        return ""
    try:
        return (
            datetime.fromtimestamp(timestamp_us / 1_000_000, tz=UTC)
            .astimezone()
            .strftime("%H:%M")
        )
    except (ValueError, OverflowError, OSError):
        return ""


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
    # QTextLayout indexes UTF-16 code units, while Python indexes Unicode points.
    # Using Python slices here drops or repeats text after an emoji on wrapped lines.
    utf16 = text.encode("utf-16-le")
    for line in lines:
        start = line.textStart() * 2
        end = start + line.textLength() * 2
        segment = utf16[start:end].decode("utf-16-le")
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
    stroke = QColor("#000000")
    stroke.setAlpha(fill.alpha())
    painter.strokePath(
        path,
        QPen(
            stroke,
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
        self.setTextFormat(Qt.TextFormat.PlainText)
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
        self._text_opacity = 100
        palette = self.palette()
        transparent = QColor(0, 0, 0, 0)
        palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(TEXT))
        palette.setColor(QPalette.ColorRole.PlaceholderText, transparent)
        self.setPalette(palette)
        self.setGraphicsEffect(TextOutlineEffect(self))

    @property
    def is_composing(self) -> bool:
        return bool(self._preedit)

    def inputMethodEvent(self, event) -> None:
        super().inputMethodEvent(event)
        self._preedit = event.preeditString()
        self.update()

    def set_text_opacity(self, percentage: int) -> None:
        self._text_opacity = max(20, min(100, percentage))
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(TEXT))
        self.setPalette(palette)
        self.graphicsEffect().set_opacity(self._text_opacity / 100)
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
        if self.hasFocus() and not self.isReadOnly():
            # Qt can suppress its caret on a translucent tool window. Use its
            # native cursor rectangle; text layout and hit testing stay native.
            rect = self.cursorRect()
            painter = QPainter(self)
            painter.fillRect(
                rect.center().x(), rect.top(), 2, rect.height(), QColor(ACCENT_HOT)
            )


class MessageComposer(QFrame):
    """A single recipient and native editor, shared by HUD and preview."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("messageComposer")
        self.setStyleSheet("""
            QFrame#messageComposer { background: transparent; border: none;
                border-top: 1px solid rgba(208,222,193,73); }
            QLineEdit { background: transparent; border: none; padding: 2px 0;
                selection-background-color: #657247; selection-color: #fffef8; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 5, 2, 0)
        root.setSpacing(2)
        layout = QHBoxLayout()
        layout.setSpacing(9)
        self.channel = OutlinedLabel()
        self.channel.setFont(_ui_font(9))
        palette = self.channel.palette()
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#d0d9cc"))
        self.channel.setPalette(palette)
        self.channel.setStyleSheet("background: transparent; color: #d0d9cc;")
        self.edit = OutlinedLineEdit()
        self.edit.setMaxLength(500)
        layout.addWidget(self.channel)
        layout.addWidget(self.edit, 1)
        root.addLayout(layout)
        self.failure = QLabel("未发送")
        self.failure.setFont(_ui_font(9))
        self.failure.setStyleSheet("color: #e7cb9c; background: transparent")
        self.failure.hide()
        root.addWidget(self.failure)
        self.edit.textEdited.connect(lambda: self.set_failed(False))

    def set_failed(self, failed: bool) -> None:
        self.failure.setVisible(failed)

    def configure(self, settings) -> None:
        destination = "# " + (settings.channel_name or "频道")
        self.channel.setText(
            self.channel.fontMetrics().elidedText(
                destination, Qt.TextElideMode.ElideRight, 95
            )
        )
        self.channel.setToolTip(destination)
        self.channel.setAccessibleName(destination)
        self.edit.setAccessibleName("发往 " + destination + " 的消息")
        self.edit.setFont(_ui_font(settings.font_size))
        self.edit.setFixedHeight(max(30, self.edit.fontMetrics().height() + 8))
        self.edit.set_text_opacity(settings.text_opacity)


class HistoryNavigation(QWidget):
    latest_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        self.time = OutlinedLabel()
        self.time.setFont(_ui_font(9))
        self.time.setStyleSheet("color: #d6ddd3; background: transparent")
        layout.addWidget(self.time)
        layout.addStretch(1)
        self.latest = QPushButton("回到最新 ↓")
        self.latest.setFont(_ui_font(9))
        self.latest.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.latest.setStyleSheet(
            "QPushButton { background: rgba(10,17,16,110); color: #e1e8cc; border: none; border-radius: 3px; padding: 2px 5px; }"
        )
        self.latest.clicked.connect(self.latest_requested.emit)
        layout.addWidget(self.latest)


class MessageRow(QWidget):
    def __init__(
        self,
        message: ChatMessage,
        font_size: int = 12,
        text_opacity: int = 100,
        highlight: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._highlight_alpha = 0
        self._highlight_animation = QVariantAnimation(self)
        self._highlight_animation.setDuration(1400)
        self._highlight_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._highlight_animation.valueChanged.connect(self._set_highlight_alpha)
        if highlight:
            self._highlight_alpha = 52
            self._highlight_animation.setStartValue(52)
            self._highlight_animation.setEndValue(0)
            self._highlight_animation.start()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 1, 3, 1)
        layout.setSpacing(6)

        moment = message_time(message.timestamp_us)
        name = "你" if message.mine else message.sender_name
        font = _ui_font(font_size, QFont.Weight.Medium)
        metrics = QFontMetricsF(font)
        name_width = round(metrics.horizontalAdvance("字字字") + 4)
        sender = OutlinedLabel(
            metrics.elidedText(name, Qt.TextElideMode.ElideRight, name_width - 4)
        )
        sender.setFixedWidth(name_width)
        sender.setToolTip(
            f"{message.sender_name} · {moment}" if moment else message.sender_name
        )
        sender.setAccessibleName(name)
        sender.setAccessibleDescription(moment)
        sender.setFont(font)
        sender_palette = sender.palette()
        sender_palette.setColor(
            QPalette.ColorRole.WindowText,
            _with_opacity("#c6d9dd" if message.mine else "#d6e0bc", text_opacity),
        )
        sender.setPalette(sender_palette)
        name_color = _with_opacity(
            "#c6d9dd" if message.mine else "#d6e0bc", text_opacity
        )
        sender.setStyleSheet(
            f"background:transparent; color:rgba{str(name_color.getRgb())};"
        )
        text = OutlinedLabel(message.text)
        text.setWordWrap(True)
        text.setFont(_ui_font(font_size))
        text_palette = text.palette()
        text_palette.setColor(
            QPalette.ColorRole.WindowText,
            _with_opacity(TEXT, text_opacity),
        )
        text.setPalette(text_palette)
        text_color = _with_opacity(TEXT, text_opacity)
        text.setStyleSheet(
            f"background:transparent; color:rgba{str(text_color.getRgb())};"
        )
        layout.addWidget(sender, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(text, 1, Qt.AlignmentFlag.AlignTop)

    @property
    def highlight_alpha(self) -> int:
        return self._highlight_alpha

    def _set_highlight_alpha(self, value) -> None:
        self._highlight_alpha = int(value)
        self.update()

    def paintEvent(self, event) -> None:
        if self._highlight_alpha:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(180, 198, 139, self._highlight_alpha))
            painter.drawRoundedRect(self.rect().adjusted(1, 0, -1, 0), 5, 5)
            painter.end()
        super().paintEvent(event)
