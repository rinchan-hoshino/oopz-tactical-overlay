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
WM_HOTKEY = 0x0312
WM_MOUSEWHEEL = 0x020A
WH_MOUSE_LL = 14
HOTKEY_ACTIVATE_ID = 0xB001
HOTKEY_VISIBILITY_ID = 0xB002
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
HWND_TOPMOST = -1
SW_SHOW = 5
SW_RESTORE = 9
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_NOOWNERZORDER = 0x0200

_MODIFIER_KEYS = {
    "ctrl": VK_CONTROL,
    "control": VK_CONTROL,
    "alt": VK_MENU,
    "shift": VK_SHIFT,
    "win": VK_LWIN,
    "meta": VK_LWIN,
}


class MouseLowLevelHookData(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


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


def _focus_window_native(user32, kernel32, window_id: int, input_id: int) -> bool:
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
        user32.ShowWindow(window_id, SW_RESTORE)
        user32.SetWindowPos(
            window_id,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | SWP_NOOWNERZORDER,
        )
        user32.BringWindowToTop(window_id)
        user32.SetForegroundWindow(window_id)
        user32.SetActiveWindow(window_id)
        user32.SetFocus(input_id)
        if int(user32.GetForegroundWindow() or 0) != window_id:
            switch_to_window = getattr(user32, "SwitchToThisWindow", None)
            if switch_to_window is not None:
                switch_to_window(window_id, True)
            user32.SetForegroundWindow(window_id)
            user32.SetFocus(input_id)
        return int(user32.GetForegroundWindow() or 0) == window_id
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, foreground_thread, False)


def focus_window(window_id: int, input_id: int) -> bool:
    if os.name != "nt":
        return False
    return _focus_window_native(
        ctypes.windll.user32,
        ctypes.windll.kernel32,
        window_id,
        input_id,
    )


def foreground_window() -> int:
    if os.name != "nt":
        return 0
    return int(ctypes.windll.user32.GetForegroundWindow() or 0)


def _restore_window_native(user32, kernel32, window_id: int) -> bool:
    if not window_id or not user32.IsWindow(window_id):
        return False
    foreground = int(user32.GetForegroundWindow() or 0)
    if foreground == window_id:
        return True
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
        if user32.IsIconic(window_id):
            user32.ShowWindow(window_id, SW_RESTORE)
        user32.BringWindowToTop(window_id)
        user32.SetForegroundWindow(window_id)
        user32.SetActiveWindow(window_id)
        if int(user32.GetForegroundWindow() or 0) != window_id:
            switch_to_window = getattr(user32, "SwitchToThisWindow", None)
            if switch_to_window is not None:
                switch_to_window(window_id, True)
        return int(user32.GetForegroundWindow() or 0) == window_id
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, foreground_thread, False)


def restore_window(window_id: int) -> bool:
    if os.name != "nt":
        return False
    return _restore_window_native(
        ctypes.windll.user32,
        ctypes.windll.kernel32,
        window_id,
    )


def ensure_window_topmost(window_id: int) -> None:
    if os.name != "nt":
        return
    ctypes.windll.user32.SetWindowPos(
        window_id,
        HWND_TOPMOST,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_NOOWNERZORDER,
    )


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
    ensure_window_topmost(window_id)


def _modifier_flags(spec: HotkeySpec) -> int:
    flags = MOD_NOREPEAT
    if spec.alt:
        flags |= MOD_ALT
    if spec.ctrl:
        flags |= MOD_CONTROL
    if spec.shift:
        flags |= MOD_SHIFT
    if spec.win:
        flags |= MOD_WIN
    return flags


class GlobalWheelRegistration:
    """Capture vertical wheel input globally while the HUD input is active."""

    def __init__(
        self,
        callback,
        *,
        user32=None,
        kernel32=None,
        install: bool = True,
    ) -> None:
        if install and os.name != "nt" and user32 is None:
            raise OSError("Global wheel capture is only available on Windows")
        self._callback = callback
        self._enabled = False
        self._user32 = user32 or (ctypes.windll.user32 if os.name == "nt" else None)
        self._kernel32 = kernel32 or (
            ctypes.windll.kernel32 if os.name == "nt" else None
        )
        self._hook = 0
        callback_factory = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
        self._procedure_type = callback_factory(
            ctypes.c_ssize_t,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        self._procedure = self._procedure_type(self._hook_procedure)
        if install:
            self._install()

    def _install(self) -> None:
        if self._user32 is None or self._kernel32 is None:
            raise OSError("Global wheel capture is unavailable")
        set_hook = self._user32.SetWindowsHookExW
        set_hook.argtypes = [
            ctypes.c_int,
            self._procedure_type,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        ]
        set_hook.restype = wintypes.HHOOK
        call_next = self._user32.CallNextHookEx
        call_next.argtypes = [
            wintypes.HHOOK,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        call_next.restype = ctypes.c_ssize_t
        unhook = self._user32.UnhookWindowsHookEx
        unhook.argtypes = [wintypes.HHOOK]
        unhook.restype = wintypes.BOOL
        get_module = self._kernel32.GetModuleHandleW
        get_module.argtypes = [wintypes.LPCWSTR]
        get_module.restype = wintypes.HINSTANCE
        module = get_module(None)
        self._hook = int(set_hook(WH_MOUSE_LL, self._procedure, module, 0) or 0)
        if not self._hook:
            raise OSError(int(self._kernel32.GetLastError()), "无法监听滚轮")

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def dispatch(self, message: int, mouse_data: int) -> bool:
        if not self._enabled or message != WM_MOUSEWHEEL:
            return False
        delta = ctypes.c_short((mouse_data >> 16) & 0xFFFF).value
        if not delta:
            return False
        self._callback(delta)
        return True

    def _hook_procedure(self, code: int, message: int, pointer: int) -> int:
        if code >= 0 and message == WM_MOUSEWHEEL:
            value = ctypes.cast(
                pointer,
                ctypes.POINTER(MouseLowLevelHookData),
            ).contents
            if self.dispatch(message, int(value.mouseData)):
                return 1
        if self._user32 is None:
            return 0
        return int(self._user32.CallNextHookEx(self._hook, code, message, pointer))

    def close(self) -> None:
        self._enabled = False
        if self._hook and self._user32 is not None:
            self._user32.UnhookWindowsHookEx(self._hook)
            self._hook = 0


class GlobalHotkeyRegistration:
    """Register Windows-owned global shortcuts on the overlay window."""

    def __init__(self, window_id: int, user32=None) -> None:
        if os.name != "nt" and user32 is None:
            raise OSError("Global hotkeys are only available on Windows")
        self._window_id = window_id
        self._user32 = user32 or ctypes.windll.user32
        self._registered: dict[int, HotkeySpec] = {}

    def configure(self, activation: str, visibility: str) -> None:
        requested = {
            HOTKEY_ACTIVATE_ID: parse_hotkey(activation),
            HOTKEY_VISIBILITY_ID: parse_hotkey(visibility),
        }
        if requested == self._registered:
            return
        previous = dict(self._registered)
        self._unregister_all()
        try:
            self._register_all(requested)
        except OSError:
            self._unregister_all()
            self._register_all(previous)
            raise

    def close(self) -> None:
        self._unregister_all()

    def _register_all(self, hotkeys: dict[int, HotkeySpec]) -> None:
        for identifier, spec in hotkeys.items():
            if not self._user32.RegisterHotKey(
                self._window_id,
                identifier,
                _modifier_flags(spec),
                spec.key,
            ):
                error_code = ctypes.get_last_error() if os.name == "nt" else 0
                raise OSError(error_code, "快捷键已被其他程序占用")
            self._registered[identifier] = spec

    def _unregister_all(self) -> None:
        for identifier in tuple(self._registered):
            self._user32.UnregisterHotKey(self._window_id, identifier)
        self._registered.clear()
