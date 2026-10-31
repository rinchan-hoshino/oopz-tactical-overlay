"""Render the checked-in SVG masters; Qt is the only rendering dependency."""
import argparse
import struct
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

ASSETS = Path(__file__).resolve().parents[2] / 'src/oopz_overlay/assets'
SIZES = (16, 20, 24, 32, 48, 64, 128, 256)


def render():
    frames = []
    for size in SIZES:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        source = ASSETS / ('icon-small.svg' if size <= 24 else 'icon.svg')
        QSvgRenderer(str(source)).render(painter)
        painter.end()
        encoded = QByteArray()
        buffer = QBuffer(encoded)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        assert image.save(buffer, 'PNG')
        data = bytes(encoded)
        (ASSETS / f'icon-{size}.png').write_bytes(data)
        frames.append(data)
    offset = 6 + 16 * len(SIZES)
    headers = []
    for size, data in zip(SIZES, frames):
        headers.append(struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    (ASSETS / 'icon.ico').write_bytes(struct.pack('<HHH', 0, 1, len(SIZES)) + b''.join(headers + frames))


def preview(path):
    width = sum(SIZES) + 9 * 28
    image = QImage(width, 650, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    painter.setFont(QFont('Arial', 12))
    for row, (background, foreground) in enumerate((('#EEF0F4', '#1B1F27'), ('#101318', '#E9ECF2'))):
        top = row * 325
        painter.fillRect(0, top, width, 325, QColor(background))
        painter.setPen(QColor(foreground))
        painter.drawText(28, top + 26, 'LIGHT TASKBAR' if row == 0 else 'DARK TASKBAR')
        x = 28
        for size in SIZES:
            painter.drawImage(x, top + 48 + (256 - size) // 2, QImage(str(ASSETS / f'icon-{size}.png')))
            painter.drawText(x, top + 322, str(size))
            x += size + 28
    painter.end()
    path.parent.mkdir(parents=True, exist_ok=True)
    assert image.save(str(path))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', type=Path)
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    render()
    if args.preview:
        preview(args.preview)
