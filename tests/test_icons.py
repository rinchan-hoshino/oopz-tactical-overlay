import struct
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from oopz_overlay.ui.tray import app_icon

ASSETS = Path(__file__).resolve().parents[1] / 'src/oopz_overlay/assets'
SIZES = (16, 20, 24, 32, 48, 64, 128, 256)


def test_exe_and_runtime_icons_use_the_same_complete_frames():
    app = QApplication.instance() or QApplication([])
    data = (ASSETS / 'icon.ico').read_bytes()
    assert struct.unpack_from('<HHH', data) == (0, 1, 8)
    icon = app_icon()
    for index, size in enumerate(SIZES):
        w, h, _, _, planes, bits, length, offset = struct.unpack_from('<BBBBHHII', data, 6 + 16 * index)
        assert (w or 256, h or 256, planes, bits) == (size, size, 1, 32)
        frame = QImage.fromData(data[offset:offset + length])
        assert frame.size() == QSize(size, size)
        assert frame == QImage(str(ASSETS / f'icon-{size}.png'))
        assert icon.actualSize(QSize(size, size)) == QSize(size, size)
        rendered = icon.pixmap(size, size).toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        assert rendered == frame.convertToFormat(rendered.format())
        # A readable sheet still occupies the center at native tray resolution.
        paper = sum(min(frame.pixelColor(x, y).getRgb()[:3]) > 220
                    for y in range(size) for x in range(size))
        assert .18 < paper / size**2 < .4
