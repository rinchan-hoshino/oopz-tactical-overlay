from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QKeyEvent
from .win32_input import parse_hotkey

ACCENT = "#60a5fa"
ACCENT_HOT = "#93c5fd"
TEXT = "#f3f4f6"
MUTED = "#9ca3af"
SURFACE = "#202124"
SURFACE_2 = "#2a2c31"
BORDER = "#3d4046"
DANGER = "#f28b82"
FONT_FAMILY = "Microsoft YaHei UI"


def _ui_font(point_size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont(FONT_FAMILY)
    font.setPointSize(point_size)
    font.setWeight(weight)
    return font


def _with_opacity(color: str, percentage: int) -> QColor:
    value = QColor(color)
    value.setAlpha(round(255 * max(0, min(100, percentage)) / 100))
    return value


_KEY_NAMES = {
    int(Qt.Key.Key_Return): "Enter",
    int(Qt.Key.Key_Enter): "Enter",
    int(Qt.Key.Key_Tab): "Tab",
    int(Qt.Key.Key_Space): "Space",
    int(Qt.Key.Key_Escape): "Escape",
    int(Qt.Key.Key_Delete): "Delete",
    int(Qt.Key.Key_Insert): "Insert",
    int(Qt.Key.Key_Home): "Home",
    int(Qt.Key.Key_End): "End",
    int(Qt.Key.Key_PageUp): "PageUp",
    int(Qt.Key.Key_PageDown): "PageDown",
    int(Qt.Key.Key_Left): "Left",
    int(Qt.Key.Key_Right): "Right",
    int(Qt.Key.Key_Up): "Up",
    int(Qt.Key.Key_Down): "Down",
}


def _hotkey_from_event(event: QKeyEvent) -> str:
    key = int(event.key())
    if int(Qt.Key.Key_A) <= key <= int(Qt.Key.Key_Z):
        key_name = chr(ord("A") + key - int(Qt.Key.Key_A))
    elif int(Qt.Key.Key_0) <= key <= int(Qt.Key.Key_9):
        key_name = chr(ord("0") + key - int(Qt.Key.Key_0))
    elif int(Qt.Key.Key_F1) <= key <= int(Qt.Key.Key_F12):
        key_name = f"F{key - int(Qt.Key.Key_F1) + 1}"
    else:
        key_name = _KEY_NAMES.get(key, "")
    if not key_name:
        raise ValueError("这个按键暂不支持")

    modifiers = event.modifiers()
    parts = []
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        parts.append("Ctrl")
    if modifiers & Qt.KeyboardModifier.AltModifier:
        parts.append("Alt")
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        parts.append("Shift")
    if modifiers & Qt.KeyboardModifier.MetaModifier:
        parts.append("Win")
    parts.append(key_name)
    value = "+".join(parts)
    parse_hotkey(value)
    return value
