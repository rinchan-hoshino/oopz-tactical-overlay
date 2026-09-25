from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsEffect


class TextOutlineEffect(QGraphicsEffect):
    """Outline the native rendered glyphs without replacing text/IME layout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.opacity = 1.0

    def set_opacity(self, value: float) -> None:
        self.opacity = max(0.0, min(1.0, value))
        self.update()

    def boundingRectFor(self, rect: QRectF) -> QRectF:
        return rect.adjusted(-1.5, -1.5, 1.5, 1.5)

    def draw(self, painter: QPainter) -> None:
        offset = QPoint()
        source = self.sourcePixmap(Qt.CoordinateSystem.LogicalCoordinates, offset)
        if source.isNull():
            return
        mask = QPixmap(source.size())
        mask.setDevicePixelRatio(source.devicePixelRatio())
        mask.fill(Qt.GlobalColor.transparent)
        brush = QPainter(mask)
        brush.drawPixmap(0, 0, source)
        brush.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        brush.fillRect(mask.rect(), QColor(0, 0, 0))
        brush.end()
        outlined = QPixmap(source.size())
        outlined.setDevicePixelRatio(source.devicePixelRatio())
        outlined.fill(Qt.GlobalColor.transparent)
        outline = QPainter(outlined)
        for x, y in (
            (-1, -1),
            (0, -1),
            (1, -1),
            (-1, 0),
            (1, 0),
            (-1, 1),
            (0, 1),
            (1, 1),
        ):
            outline.drawPixmap(QPointF(x, y), mask)
        outline.drawPixmap(0, 0, source)
        outline.end()
        painter.save()
        painter.setOpacity(self.opacity)
        painter.drawPixmap(offset, outlined)
        painter.restore()
