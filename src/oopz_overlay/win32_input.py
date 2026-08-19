from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass

VK_RETURN = 0x0D
VK_TAB = 0x09
VK_SPACE = 0x20
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_ESCAPE = 0x1B
VK_PRIOR = 0x21
VK_NEXT = 0x22
VK_END = 0x23
VK_HOME = 0x24
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_INSERT = 0x2D
VK_DELETE = 0x2E
VK_LWIN = 0x5B
VK_RWIN = 0x5C
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
SW_SHOW = 5

_MODIFIER_KEYS = {
    "ctrl": VK_CONTROL,
    "control": VK_CONTROL,
    "alt": VK_MENU,
    "shift": VK_SHIFT,
    "win": VK_LWIN,
    "meta": VK_LWIN,
}
_NAMED_KEYS = {
    "enter": VK_RETURN,
    "return": VK_RETURN,
    "tab": VK_TAB,
    "space": VK_SPACE,
    "escape": VK_ESCAPE,
    "esc": VK_ESCAPE,
    "pageup": VK_PRIOR,
    "pagedown": VK_NEXT,
    "end": VK_END,
    "home": VK_HOME,
    "left": VK_LEFT,
    "up": VK_UP,
    "right": VK_RIGHT,
    "down": VK_DOWN,
    "insert": VK_INSERT,
    "delete": VK_DELETE,
}


@dataclass(frozen=True, slots=True)
class HotkeySpec:
    key: int
    ctrl: bool = False
    alt: bool = False
    shift: bool = False
    win: bool = False


def parse_hotkey(value: str) -> HotkeySpec:
    parts = [part.strip().casefold() for part in value.split("+") if part.strip()]
    if not parts:
        raise ValueError("快捷键不能为空")

    modifiers = {part for part in parts if part in _MODIFIER_KEYS}
    keys = [part for part in parts if part not in _MODIFIER_KEYS]
    if len(keys) != 1:
        raise ValueError("快捷键需要且只能包含一个主按键")

    name = keys[0]
    if name in _NAMED_KEYS:
        key = _NAMED_KEYS[name]
    elif len(name) == 1 and name.isascii() and name.isalnum():
        key = ord(name.upper())
    elif name.startswith("f") and name[1:].isdigit() and 1 <= int(name[1:]) <= 12:
        key = 0x70 + int(name[1:]) - 1
    else:
        raise ValueError("支持常用功能键、A-Z、0-9 与 F1-F12")

    return HotkeySpec(
        key=key,
        ctrl=bool(modifiers & {"ctrl", "control"}),
        alt="alt" in modifiers,
        shift="shift" in modifiers,
        win=bool(modifiers & {"win", "meta"}),
    )


def focus_window(window_id: int, input_id: int) -> bool:
    if os.name != "nt":
        return False
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    foreground = int(user32.GetForegroundWindow() or 0)
    foreground_thread = (
        int(user32.GetWindowThreadProcessId(foreground, None)) if foreground else 0
    )
    current_thread = int(kernel32.GetCurrentThreadId())
    attached = bool(
        foreground_thread
        and foreground_thread != current_thread
        and user32.AttachThreadInput(current_thread, foreground_thread, True)
    )
    try:
        user32.ShowWindow(window_id, SW_SHOW)
        user32.BringWindowToTop(window_id)
        user32.SetForegroundWindow(window_id)
        user32.SetActiveWindow(window_id)
        user32.SetFocus(input_id)
        return int(user32.GetForegroundWindow() or 0) == window_id
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, foreground_thread, False)


def prepare_input_method(input_id: int) -> bool:
    """Attach the current Windows IME to the editor and open it for text input."""
    if os.name != "nt":
        return False
    imm32 = ctypes.windll.imm32
    imm32.ImmAssociateContextEx(wintypes.HWND(input_id), None, 0x10)
    context = imm32.ImmGetContext(wintypes.HWND(input_id))
    if not context:
        return False
    try:
        return bool(imm32.ImmSetOpenStatus(context, True))
    finally:
        imm32.ImmReleaseContext(wintypes.HWND(input_id), context)


def set_window_click_through(window_id: int, enabled: bool) -> None:
    """Toggle native click-through without installing a window or keyboard hook."""
    if os.name != "nt":
        return
    user32 = ctypes.windll.user32
    get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    get_style.argtypes = [wintypes.HWND, ctypes.c_int]
    get_style.restype = ctypes.c_ssize_t
    set_style.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    set_style.restype = ctypes.c_ssize_t
    style = int(get_style(window_id, GWL_EXSTYLE))
    passive_bits = WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
    style = style | passive_bits if enabled else style & ~passive_bits
    set_style(window_id, GWL_EXSTYLE, style)


class GlobalHotkeyMonitor:
    """Observe a global hotkey without hooks or foreground-process inspection."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("Global input monitoring is only available on Windows")
        self._states: dict[str, bool] = {}
        self._specs: dict[str, HotkeySpec] = {}
        self._user32 = ctypes.windll.user32

    def hotkey_pressed(self, hotkey: str) -> bool:
        spec = self._specs.get(hotkey)
        if spec is None:
            spec = parse_hotkey(hotkey)
            self._specs[hotkey] = spec
        modifier_state = {
            "ctrl": self._is_down(VK_CONTROL),
            "alt": self._is_down(VK_MENU),
            "shift": self._is_down(VK_SHIFT),
            "win": self._is_down(VK_LWIN) or self._is_down(VK_RWIN),
        }
        modifiers_match = (
            modifier_state["ctrl"] is spec.ctrl
            and modifier_state["alt"] is spec.alt
            and modifier_state["shift"] is spec.shift
            and modifier_state["win"] is spec.win
        )
        down = self._is_down(spec.key) and modifiers_match
        pressed = down and not self._states.get(hotkey, False)
        self._states[hotkey] = down
        return pressed

    def _is_down(self, virtual_key: int) -> bool:
        return bool(self._user32.GetAsyncKeyState(virtual_key) & 0x8000)
