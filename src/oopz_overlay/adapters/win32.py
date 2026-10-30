from __future__ import annotations

import ctypes
import os
import threading
from functools import lru_cache
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
    # A registered hotkey supplies user intent. Never attach another application's
    # input queue, synthesize Alt-Tab, or alter its window placement to obtain focus.
    user32.SetForegroundWindow(window_id)
    if int(user32.GetForegroundWindow() or 0) != window_id:
        return False
    user32.SetFocus(input_id)
    return True


@lru_cache(maxsize=1)
def _user32():
    api = ctypes.WinDLL("user32", use_last_error=True)
    signatures = {
        "GetForegroundWindow": ([], wintypes.HWND),
        "SetForegroundWindow": ([wintypes.HWND], wintypes.BOOL),
        "SetFocus": ([wintypes.HWND], wintypes.HWND),
        "IsWindow": ([wintypes.HWND], wintypes.BOOL),
        "IsIconic": ([wintypes.HWND], wintypes.BOOL),
        "SetWindowPos": (
            [
                wintypes.HWND,
                wintypes.HWND,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                wintypes.UINT,
            ],
            wintypes.BOOL,
        ),
        "RegisterHotKey": (
            [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT],
            wintypes.BOOL,
        ),
        "UnregisterHotKey": ([wintypes.HWND, ctypes.c_int], wintypes.BOOL),
        "PostThreadMessageW": (
            [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM],
            wintypes.BOOL,
        ),
    }
    for name, (args, result) in signatures.items():
        function = getattr(api, name)
        function.argtypes = args
        function.restype = result
    return api


def focus_window(window_id: int, input_id: int) -> bool:
    if os.name != "nt":
        return False
    return _focus_window_native(
        _user32(),
        ctypes.windll.kernel32,
        window_id,
        input_id,
    )


def foreground_window() -> int:
    if os.name != "nt":
        return 0
    return int(_user32().GetForegroundWindow() or 0)


def _restore_window_native(
    user32, kernel32, window_id: int, expected_foreground: int = 0
) -> bool:
    if not window_id or not user32.IsWindow(window_id):
        return False
    foreground = int(user32.GetForegroundWindow() or 0)
    if foreground == window_id:
        return True
    if expected_foreground and foreground not in {0, expected_foreground}:
        return False
    if user32.IsIconic(window_id):
        return False
    user32.SetForegroundWindow(window_id)
    return int(user32.GetForegroundWindow() or 0) == window_id


def restore_window(window_id: int, expected_foreground: int = 0) -> bool:
    if os.name != "nt":
        return False
    return _restore_window_native(
        _user32(),
        ctypes.windll.kernel32,
        window_id,
        expected_foreground,
    )


def ensure_window_topmost(window_id: int) -> None:
    if os.name != "nt":
        return
    _user32().SetWindowPos(
        window_id,
        HWND_TOPMOST,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_NOOWNERZORDER,
    )


def prepare_input_method(input_id: int) -> bool:
    """Attach an IME context without changing the user's input mode."""
    if os.name != "nt":
        return False
    imm32 = ctypes.WinDLL("imm32", use_last_error=True)
    imm32.ImmAssociateContextEx.argtypes = [
        wintypes.HWND,
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    imm32.ImmAssociateContextEx.restype = wintypes.BOOL
    imm32.ImmGetContext.argtypes = [wintypes.HWND]
    imm32.ImmGetContext.restype = wintypes.HANDLE
    imm32.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
    imm32.ImmReleaseContext.restype = wintypes.BOOL
    context = imm32.ImmGetContext(wintypes.HWND(input_id))
    if not context:
        imm32.ImmAssociateContextEx(wintypes.HWND(input_id), None, 0x10)
        context = imm32.ImmGetContext(wintypes.HWND(input_id))
    if not context:
        return False
    try:
        # Preserve the user's IME mode instead of forcing Chinese/English globally.
        return True
    finally:
        imm32.ImmReleaseContext(wintypes.HWND(input_id), context)


def set_window_click_through(window_id: int, enabled: bool) -> None:
    """Toggle native click-through without installing a window or keyboard hook."""
    if os.name != "nt":
        return
    user32 = _user32()
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
        window_id: int = 0,
        on_error=None,
    ) -> None:
        if install and os.name != "nt" and user32 is None:
            raise OSError("Global wheel capture is only available on Windows")
        self._callback = callback
        self._enabled = False
        self._user32 = user32 or (_user32() if os.name == "nt" else None)
        self._kernel32 = kernel32 or (
            ctypes.windll.kernel32 if os.name == "nt" else None
        )
        self._hook = 0
        self._window_id = window_id
        self._install_requested = install
        self._thread = None
        self._thread_id = 0
        self._thread_ready = threading.Event()
        self._closed = False
        self._on_error = on_error
        callback_factory = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
        self._procedure_type = callback_factory(
            ctypes.c_ssize_t,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        self._procedure = self._procedure_type(self._hook_procedure)
        if self._install_requested:
            self._start_worker()

    def _start_worker(self) -> None:
        self._thread_ready.clear()
        self._thread_id = 0
        self._thread = threading.Thread(
            target=self._pump, name="oopz-wheel", daemon=True
        )
        self._thread.start()

    def _sync_hook(self) -> None:
        if self._enabled and not self._hook:
            self._install()
        elif not self._enabled and self._hook:
            self._user32.UnhookWindowsHookEx(self._hook)
            self._hook = 0

    def _pump(self) -> None:
        self._thread_id = int(self._kernel32.GetCurrentThreadId())
        message = wintypes.MSG()
        self._user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        self._thread_ready.set()
        try:
            # close() may run before this thread creates its Windows queue.
            # In that case a posted WM_QUIT cannot arrive; exit here instead.
            if self._closed:
                return
            self._sync_hook()
            while self._user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == 0x8001:
                    self._sync_hook()
                else:
                    self._user32.TranslateMessage(ctypes.byref(message))
                    self._user32.DispatchMessageW(ctypes.byref(message))
        except Exception as exc:
            self._enabled = False
            if self._on_error is not None:
                self._on_error(f"滚轮监听暂时不可用：{exc}")
        finally:
            if self._hook:
                self._user32.UnhookWindowsHookEx(self._hook)
                self._hook = 0

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
        if self._closed:
            return
        self._enabled = enabled
        if not self._install_requested:
            return
        if enabled and (self._thread is None or not self._thread.is_alive()):
            self._start_worker()
        if self._thread_ready.is_set():
            self._user32.PostThreadMessageW(self._thread_id, 0x8001, 0, 0)

    def dispatch(self, message: int, mouse_data: int) -> bool:
        if not self._enabled or message != WM_MOUSEWHEEL:
            return False
        if (
            self._window_id
            and int(self._user32.GetForegroundWindow() or 0) != self._window_id
        ):
            return False
        delta = ctypes.c_short((mouse_data >> 16) & 0xFFFF).value
        if not delta:
            return False
        return self._callback(delta) is not False

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
        self._closed = True
        self._enabled = False
        if self._thread is not None:
            self._user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
            self._thread.join(timeout=1)
        elif self._hook and self._user32 is not None:
            self._user32.UnhookWindowsHookEx(self._hook)
            self._hook = 0


class GlobalHotkeyRegistration:
    """Register Windows-owned global shortcuts on the overlay window."""

    def __init__(self, window_id: int, user32=None) -> None:
        if os.name != "nt" and user32 is None:
            raise OSError("Global hotkeys are only available on Windows")
        self._window_id = window_id
        self._user32 = user32 or _user32()
        self._registered: dict[int, HotkeySpec] = {}
        self._requested: tuple[str, str] | None = None
        self._paused = False

    def set_paused(self, paused: bool) -> None:
        if paused == self._paused:
            return
        self._paused = paused
        if paused:
            self._unregister_all()
        elif self._requested is not None:
            self.configure(*self._requested)

    def configure(self, activation: str, visibility: str) -> None:
        requested = {
            HOTKEY_ACTIVATE_ID: parse_hotkey(activation),
            HOTKEY_VISIBILITY_ID: parse_hotkey(visibility),
        }
        if requested[HOTKEY_ACTIVATE_ID] == requested[HOTKEY_VISIBILITY_ID]:
            raise ValueError("输入和显示快捷键不能相同")
        if self._paused:
            self._requested = (activation, visibility)
            return
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
        self._requested = (activation, visibility)

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


def instance_name(state_root) -> str:
    import hashlib
    return 'oopz-overlay-' + hashlib.sha256(str(state_root).encode()).hexdigest()[:16]


"""Discover and play the sounds installed with the current Windows system."""


import os
import sys
from pathlib import Path


def _media_root() -> Path | None:
    if sys.platform != "win32":
        return None
    return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Media"


def system_sounds() -> list[tuple[str, str]]:
    """Return display names and relative filenames, without bundling audio."""
    root = _media_root()
    if root is None:
        return []
    try:
        files = sorted(root.rglob("*.wav"), key=lambda path: str(path).casefold())
        return [
            (
                str(path.relative_to(root).with_suffix("")),
                path.relative_to(root).as_posix(),
            )
            for path in files
            if path.is_file() and path.resolve().is_relative_to(root.resolve())
        ]
    except OSError:
        return []


def play_sound(key: str, *, preview: bool = False) -> bool:
    root = _media_root()
    if not key or root is None:
        return False
    try:
        path = (root / key).resolve()
        if (
            not path.is_relative_to(root.resolve())
            or path.suffix.casefold() != ".wav"
            or not path.is_file()
        ):
            return False
        import winsound

        flags = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
        if not preview:
            flags |= winsound.SND_NOSTOP
        winsound.PlaySound(str(path), flags)
        return True
    except (OSError, RuntimeError, ValueError):
        # A removed file, busy sound, or unavailable device must not affect chat.
        return False


def control_pressed() -> bool:
    return os.name == 'nt' and bool(_user32().GetAsyncKeyState(VK_CONTROL) & 0x8000)
