from __future__ import annotations
from .i18n import tr

from datetime import UTC, datetime
from math import ceil
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
    QTextOption,
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


def _wrapped_text_layout(text: str, font: QFont, width: float) -> QTextLayout:
    layout = QTextLayout(text, font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.beginLayout()
    y = 0.0
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(max(1.0, width))
        line.setPosition(QPointF(0.0, y))
        y += line.height()
    layout.endLayout()
    return layout


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

    layout = _wrapped_text_layout(text, font, rect.width())
    # QTextLayout indexes UTF-16 code units, while Python indexes Unicode points.
    # Using Python slices here drops or repeats text after an emoji on wrapped lines.
    utf16 = text.encode("utf-16-le")
    for index in range(layout.lineCount()):
        line = layout.lineAt(index)
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

    def heightForWidth(self, width: int) -> int:
        if not self.wordWrap():
            return super().heightForWidth(width)
        margins = self.contentsMargins()
        layout = _wrapped_text_layout(
            self.text(), self.font(), width - margins.left() - margins.right()
        )
        return ceil(layout.boundingRect().height()) + margins.top() + margins.bottom()

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
        self._style = """
            QFrame#messageComposer { background: transparent; border: none; }
            QLineEdit { background: transparent; border: none; padding: 2px 0;
                border-bottom: 1px solid rgba(138,204,255,180);
                selection-background-color: #0071e3; selection-color: #ffffff; }
        """
        self.setStyleSheet(self._style)
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 5, 2, 0)
        root.setSpacing(2)
        layout = QHBoxLayout()
        layout.setSpacing(9)
        self.channel = OutlinedLabel()
        self.channel.setFont(_ui_font(9))
        palette = self.channel.palette()
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#8accff"))
        self.channel.setPalette(palette)
        self.channel.setStyleSheet("background: transparent; color: #8accff;")
        self.edit = OutlinedLineEdit()
        self.edit.setMaxLength(500)
        layout.addWidget(self.channel)
        layout.addWidget(self.edit, 1)
        root.addLayout(layout)
        self.failure = QLabel(tr("未发送"))
        self.failure.setFont(_ui_font(9))
        self.failure.setStyleSheet("color: #e7cb9c; background: transparent")
        self.failure.hide()
        root.addWidget(self.failure)
        self.edit.textEdited.connect(lambda: self.set_failed(False))

    def set_failed(self, failed: bool) -> None:
        self.failure.setVisible(failed)

    def configure(self, settings) -> None:
        self.setStyleSheet(self._style +
            f'QFrame#messageComposer {{ background:rgba(10,17,16,{round(settings.backdrop_opacity * 2.55)}); border-radius:3px; }}')
        destination = "# " + (settings.channel_name or tr("频道"))
        self.channel.setText(
            self.channel.fontMetrics().elidedText(
                destination, Qt.TextElideMode.ElideRight, 95
            )
        )
        self.channel.setToolTip(destination)
        self.channel.setAccessibleName(destination)
        self.edit.setAccessibleName(tr("发往 ") + destination + tr(" 的消息"))
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
        self.latest = QPushButton(tr("回到最新 ↓"))
        self.latest.setFont(_ui_font(9))
        self.latest.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.latest.setStyleSheet(
            "QPushButton { background: rgba(10,17,16,110); color: #e1e8cc; border: none; border-radius: 3px; padding: 2px 5px; }"
        )
        self.latest.clicked.connect(self.latest_requested.emit)
        layout.addWidget(self.latest)


def sender_column_width(
    messages: list[ChatMessage], font_size: int, row_width: int
) -> int:
    """Fit the names while reserving at least 60% of the row for the message."""
    metrics = QFontMetricsF(_ui_font(font_size, QFont.Weight.Medium))
    natural_width = max(
        (
            metrics.horizontalAdvance(tr("你") if m.mine else m.sender_name)
            for m in messages
        ),
        default=0,
    )
    # Row margins and the column gap use 12 px; label margins use another 4 px.
    return min(ceil(natural_width) + 4, max(1, int((row_width - 12) * 0.4)))


class MessageRow(QWidget):
    def __init__(
        self,
        message: ChatMessage,
        font_size: int = 12,
        text_opacity: int = 100,
        highlight: bool = False,
        parent: QWidget | None = None,
        *,
        sender_width: int | None = None,
        backdrop_opacity: int = 32,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._backdrop_opacity = backdrop_opacity
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
        name = tr("你") if message.mine else message.sender_name
        font = _ui_font(font_size, QFont.Weight.Medium)
        metrics = QFontMetricsF(font)
        sender = self._sender = OutlinedLabel(name)
        sender.setWordWrap(True)
        self.set_sender_width(
            sender_width
            if sender_width is not None
            else ceil(metrics.horizontalAdvance(name)) + 4
        )
        sender.setToolTip(
            f"{message.sender_name} · {moment}" if moment else message.sender_name
        )
        sender.setAccessibleName(name)
        sender.setAccessibleDescription(moment)
        sender.setFont(font)
        sender_palette = sender.palette()
        sender_palette.setColor(
            QPalette.ColorRole.WindowText,
            _with_opacity("#8accff", text_opacity),
        )
        sender.setPalette(sender_palette)
        name_color = _with_opacity("#8accff", text_opacity)
        sender.setStyleSheet(
            f"background:transparent; color:rgba{str(name_color.getRgb())};"
        )
        text = self._text = OutlinedLabel(message.text)
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

    def set_sender_width(self, width: int) -> None:
        self._sender.setFixedWidth(width)

    @property
    def highlight_alpha(self) -> int:
        return self._highlight_alpha

    def _set_highlight_alpha(self, value) -> None:
        self._highlight_alpha = int(value)
        self.update()

    def paintEvent(self, event) -> None:
        if self._backdrop_opacity or self._highlight_alpha:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            text_width = self._text.fontMetrics().horizontalAdvance(self._text.text())
            fitted_right = min(self.width() - 1, self._text.x() + text_width + 3)
            backing = QRectF(0, 0, fitted_right, self.height())
            if self._backdrop_opacity:
                painter.setBrush(QColor(10, 17, 16, round(self._backdrop_opacity * 2.55)))
                painter.drawRoundedRect(backing, 3, 3)
            if self._highlight_alpha:
                painter.setBrush(QColor(138, 204, 255, self._highlight_alpha))
                painter.drawRoundedRect(backing, 3, 3)
            painter.end()
        super().paintEvent(event)
