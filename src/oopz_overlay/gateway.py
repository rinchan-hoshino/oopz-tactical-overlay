from __future__ import annotations

import ctypes
import hashlib
import logging
import os
import queue
import re
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from .chat import ChatMessage

LOGGER = logging.getLogger(__name__)
_DATE_RE = re.compile(r"^(\d{4})年(\d{2})月(\d{2})日$")
_CLOCK_RE = re.compile(r"(\d{1,2}):(\d{2})$")


@dataclass(slots=True)
class GatewayCallbacks:
    timeline: Callable[[list[ChatMessage]], None]
    status: Callable[[str, bool], None]
    error: Callable[[str], None]
    channel: Callable[[str], None]


class OopzCompanionError(RuntimeError):
    pass


class CompanionBackend(Protocol):
    def prepare(self) -> None: ...

    def current_channel(self) -> str: ...

    def visible_messages(self) -> list[ChatMessage]: ...

    def send_message(self, text: str) -> None: ...

    def release(self) -> None: ...


def _parse_message_header(name: str) -> tuple[datetime, str, list[str]] | None:
    lines = [line.strip() for line in name.splitlines() if line.strip()]
    if len(lines) < 3:
        return None
    date_match = _DATE_RE.fullmatch(lines[0])
    clock_match = _CLOCK_RE.search(lines[2])
    if date_match is None or clock_match is None:
        return None
    value = datetime(
        int(date_match.group(1)),
        int(date_match.group(2)),
        int(date_match.group(3)),
        int(clock_match.group(1)),
        int(clock_match.group(2)),
        tzinfo=datetime.now().astimezone().tzinfo,
    )
    return value, lines[1], lines[3:]


def messages_from_accessible_rows(
    rows: Sequence[tuple[str, str, int]],
) -> list[ChatMessage]:
    """Convert Oopz's visible accessibility rows into HUD text messages."""
    assembled: list[tuple[datetime, str, list[str]]] = []
    current: tuple[datetime, str, list[str]] | None = None
    for role, name, _top in sorted(rows, key=lambda item: item[2]):
        if role == "GroupControl":
            parsed = _parse_message_header(name)
            if parsed is None:
                continue
            current = parsed
            assembled.append(current)
            continue
        if role == "TextControl" and current is not None:
            text = name.strip()
            if text:
                current[2].append(text)

    output: list[ChatMessage] = []
    occurrences: dict[str, int] = {}
    for timestamp, sender, parts in assembled:
        text = "\n".join(parts).strip()
        if not text:
            continue
        identity = f"{timestamp.isoformat()}\0{sender}\0{text}"
        ordinal = occurrences.get(identity, 0)
        occurrences[identity] = ordinal + 1
        message_id = hashlib.sha1(f"{identity}\0{ordinal}".encode()).hexdigest()
        output.append(
            ChatMessage(
                message_id=message_id,
                timestamp_us=int(timestamp.timestamp() * 1_000_000),
                sender_id=sender,
                sender_name=sender,
                text=text,
                mine=False,
            )
        )
    return output


class WindowsOopzBackend:
    WINDOW_CLASS = "XX_INFICITY_RUNNER_WIN32_WINDOW"
    WINDOW_TITLE = "Oopz"
    FLUTTER_CLASS = "FLUTTERVIEW"
    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    LWA_ALPHA = 0x00000002
    SW_RESTORE = 9
    SW_SHOWMINNOACTIVE = 7
    HWND_BOTTOM = 1
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_NOACTIVATE = 0x0010
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004

    def __init__(self) -> None:
        if os.name != "nt":
            raise OopzCompanionError("Oopz companion is only available on Windows")
        from ctypes import wintypes

        import uiautomation as auto

        self.auto = auto
        self.wintypes = wintypes
        self.user32 = ctypes.windll.user32
        self._hwnd = 0
        self._flutter_hwnd = 0
        self._originally_minimized = False
        self._originally_hidden = False
        self._original_exstyle: int | None = None
        self._foreground_owner = 0
        self._managed_hidden = False
        self._uia_context: Any | None = None

    def open_thread(self) -> None:
        self._uia_context = self.auto.UIAutomationInitializerInThread()
        self._uia_context.__enter__()

    def close_thread(self) -> None:
        if self._uia_context is not None:
            self._uia_context.__exit__(None, None, None)
            self._uia_context = None

    def _find_window(self) -> int:
        return int(self.user32.FindWindowW(self.WINDOW_CLASS, self.WINDOW_TITLE) or 0)

    def _set_alpha(self, alpha: int) -> None:
        if not self._hwnd:
            return
        if self._original_exstyle is None:
            self._original_exstyle = int(
                self.user32.GetWindowLongW(self._hwnd, self.GWL_EXSTYLE)
            )
        self.user32.SetWindowLongW(
            self._hwnd,
            self.GWL_EXSTYLE,
            self._original_exstyle | self.WS_EX_LAYERED,
        )
        self.user32.SetLayeredWindowAttributes(
            self._hwnd, 0, max(1, min(255, alpha)), self.LWA_ALPHA
        )
        if alpha >= 255 and not (self._original_exstyle & self.WS_EX_LAYERED):
            self.user32.SetWindowLongW(
                self._hwnd, self.GWL_EXSTYLE, self._original_exstyle
            )

    def _best_owner_window(self) -> int:
        current = int(self.user32.GetForegroundWindow() or 0)
        own_pid = os.getpid()

        def usable(hwnd: int) -> bool:
            if not hwnd or hwnd == self._hwnd:
                return False
            if not self.user32.IsWindowVisible(hwnd):
                return False
            pid = self.wintypes.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if int(pid.value) == own_pid:
                return False
            length = int(self.user32.GetWindowTextLengthW(hwnd))
            if length <= 0:
                return False
            title = ctypes.create_unicode_buffer(length + 1)
            self.user32.GetWindowTextW(hwnd, title, length + 1)
            return not title.value.startswith(("Oopz", "Program Manager"))

        if usable(current):
            return current
        found: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(
            self.wintypes.BOOL, self.wintypes.HWND, self.wintypes.LPARAM
        )

        def visit(hwnd: int, _parameter: int) -> bool:
            if usable(int(hwnd)):
                found.append(int(hwnd))
                return False
            return True

        self.user32.EnumWindows(callback_type(visit), 0)
        return found[0] if found else 0

    def _render_behind_foreground(self) -> None:
        if self.user32.IsWindowVisible(self._hwnd) and not self.user32.IsIconic(
            self._hwnd
        ):
            return
        self._foreground_owner = self._best_owner_window()
        self._managed_hidden = True
        self._set_alpha(1)
        self.user32.ShowWindow(self._hwnd, self.SW_RESTORE)
        for delay in (0.15, 0.35, 0.70, 1.20):
            self.user32.SetWindowPos(
                self._hwnd,
                self.HWND_BOTTOM,
                0,
                0,
                0,
                0,
                self.SWP_NOMOVE | self.SWP_NOSIZE | self.SWP_NOACTIVATE,
            )
            time.sleep(delay)
            if self._foreground_owner and self.user32.IsWindow(self._foreground_owner):
                self.user32.SetForegroundWindow(self._foreground_owner)

    def _restore_visible_background(self) -> None:
        if not self._managed_hidden:
            return
        self.user32.SetWindowPos(
            self._hwnd,
            self.HWND_BOTTOM,
            0,
            0,
            0,
            0,
            self.SWP_NOMOVE | self.SWP_NOSIZE | self.SWP_NOACTIVATE,
        )
        self._set_alpha(255)
        if self._foreground_owner and self.user32.IsWindow(self._foreground_owner):
            self.user32.SetForegroundWindow(self._foreground_owner)

    def prepare(self) -> None:
        hwnd = self._find_window()
        if not hwnd:
            raise OopzCompanionError("请先打开并登录 Oopz")
        if hwnd != self._hwnd:
            self._hwnd = hwnd
            self._flutter_hwnd = int(
                self.user32.FindWindowExW(hwnd, 0, self.FLUTTER_CLASS, None) or hwnd
            )
            self._originally_minimized = bool(self.user32.IsIconic(hwnd))
            self._originally_hidden = not bool(self.user32.IsWindowVisible(hwnd))
            self._original_exstyle = int(
                self.user32.GetWindowLongW(hwnd, self.GWL_EXSTYLE)
            )
        self._render_behind_foreground()
        if self.user32.IsIconic(hwnd) or not self.user32.IsWindowVisible(hwnd):
            raise OopzCompanionError("Oopz 窗口未能进入后台运行")
        if self._managed_hidden:
            foreground = int(self.user32.GetForegroundWindow() or 0)
            if foreground and foreground != self._hwnd:
                self._foreground_owner = foreground
            elif (
                foreground == self._hwnd
                and self._foreground_owner
                and self.user32.IsWindow(self._foreground_owner)
            ):
                self.user32.SetForegroundWindow(self._foreground_owner)
        self._restore_visible_background()

    def _window_control(self):
        window = self.auto.WindowControl(searchDepth=1, Name=self.WINDOW_TITLE)
        if not window.Exists(2, 0.1):
            raise OopzCompanionError("没有找到 Oopz 窗口")
        return window

    @staticmethod
    def _children(control: Any) -> list[Any]:
        try:
            return list(control.GetChildren() or [])
        except Exception:  # noqa: BLE001 - stale UIA nodes can fail generically
            return []

    def _walk(self, control: Any, depth: int = 0) -> Iterable[Any]:
        if depth > 24:
            return
        yield control
        for child in self._children(control):
            yield from self._walk(child, depth + 1)

    @staticmethod
    def _rect(control: Any) -> tuple[int, int, int, int] | None:
        try:
            value = control.BoundingRectangle
            return int(value.left), int(value.top), int(value.right), int(value.bottom)
        except Exception:  # noqa: BLE001 - stale UIA nodes can fail generically
            return None

    def _input_control(self) -> Any:
        prefix = "发送至频道 "
        for control in self._walk(self._window_control()):
            try:
                if control.ControlTypeName != "TextControl":
                    continue
                name = str(control.Name or "")
            except Exception:  # noqa: BLE001,S112 - skip stale UIA nodes
                continue
            if name.startswith(prefix):
                return control
        raise OopzCompanionError("Oopz 当前没有打开文字频道")

    def current_channel(self) -> str:
        self.prepare()
        name = str(self._input_control().Name or "")
        return name.removeprefix("发送至频道 ").strip()

    def visible_messages(self) -> list[ChatMessage]:
        self.prepare()
        input_control = self._input_control()
        input_rect = self._rect(input_control)
        if input_rect is None:
            return []
        left_edge = input_rect[0] - 80
        right_edge = input_rect[2] + 320
        bottom = input_rect[1]
        rows: list[tuple[str, str, int]] = []
        for control in self._walk(self._window_control()):
            try:
                role = str(control.ControlTypeName or "")
                name = str(control.Name or "")
            except Exception:  # noqa: BLE001,S112 - skip stale UIA nodes
                continue
            if role not in {"GroupControl", "TextControl"} or not name:
                continue
            rect = self._rect(control)
            if (
                rect is None
                or rect[1] < 100
                or rect[1] >= bottom
                or not (left_edge <= rect[0] <= left_edge + 120)
                or rect[2] > right_edge
            ):
                continue
            if role == "GroupControl" and _parse_message_header(name) is None:
                continue
            rows.append((role, name, rect[1]))
        return messages_from_accessible_rows(rows)

    @staticmethod
    def _keyboard_types():
        from ctypes import wintypes

        pointer = (
            ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32
        )

        class KeyboardInput(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", pointer),
            ]

        class MouseInput(ctypes.Structure):
            _fields_ = [
                ("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", pointer),
            ]

        class HardwareInput(ctypes.Structure):
            _fields_ = [
                ("uMsg", wintypes.DWORD),
                ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD),
            ]

        class InputUnion(ctypes.Union):
            _fields_ = [  # noqa: RUF012 - ctypes field declaration
                ("ki", KeyboardInput),
                ("mi", MouseInput),
                ("hi", HardwareInput),
            ]

        class Input(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("union", InputUnion)]

        return KeyboardInput, InputUnion, Input

    def _send_unicode(self, text: str) -> None:
        KeyboardInput, InputUnion, Input = self._keyboard_types()
        events: list[Any] = []
        utf16 = text.encode("utf-16-le")
        for index in range(0, len(utf16), 2):
            unit = int.from_bytes(utf16[index : index + 2], "little")
            events.extend(
                (
                    Input(
                        self.INPUT_KEYBOARD,
                        InputUnion(
                            ki=KeyboardInput(0, unit, self.KEYEVENTF_UNICODE, 0, 0)
                        ),
                    ),
                    Input(
                        self.INPUT_KEYBOARD,
                        InputUnion(
                            ki=KeyboardInput(
                                0,
                                unit,
                                self.KEYEVENTF_UNICODE | self.KEYEVENTF_KEYUP,
                                0,
                                0,
                            )
                        ),
                    ),
                )
            )
        if events:
            array = (Input * len(events))(*events)
            sent = int(self.user32.SendInput(len(events), array, ctypes.sizeof(Input)))
            if sent != len(events):
                raise OopzCompanionError("无法把文字交给 Oopz 输入框")

    def _send_key(self, virtual_key: int) -> None:
        KeyboardInput, InputUnion, Input = self._keyboard_types()
        events = (Input * 2)(
            Input(
                self.INPUT_KEYBOARD,
                InputUnion(ki=KeyboardInput(virtual_key, 0, 0, 0, 0)),
            ),
            Input(
                self.INPUT_KEYBOARD,
                InputUnion(
                    ki=KeyboardInput(virtual_key, 0, self.KEYEVENTF_KEYUP, 0, 0)
                ),
            ),
        )
        if self.user32.SendInput(2, events, ctypes.sizeof(Input)) != 2:
            raise OopzCompanionError("无法让 Oopz 发送消息")

    def _physical_click(self, rect: tuple[int, int, int, int]) -> None:
        class Point(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        old = Point()
        self.user32.GetCursorPos(ctypes.byref(old))
        try:
            self.user32.SetCursorPos((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)
            self.user32.mouse_event(self.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            self.user32.mouse_event(self.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        finally:
            self.user32.SetCursorPos(old.x, old.y)

    def send_message(self, text: str) -> None:
        value = text.strip()
        if not value:
            return
        self.prepare()
        foreground = int(self.user32.GetForegroundWindow() or 0)
        input_rect = self._rect(self._input_control())
        if input_rect is None:
            raise OopzCompanionError("没有找到 Oopz 文字输入框")
        self._set_alpha(1)
        try:
            self.user32.SetForegroundWindow(self._hwnd)
            time.sleep(0.12)
            self._physical_click(input_rect)
            time.sleep(0.12)
            self._send_unicode(value)
            self._send_key(0x0D)
            time.sleep(0.12)
        finally:
            if foreground and self.user32.IsWindow(foreground):
                self.user32.SetForegroundWindow(foreground)
            self.user32.SetWindowPos(
                self._hwnd,
                self.HWND_BOTTOM,
                0,
                0,
                0,
                0,
                self.SWP_NOMOVE | self.SWP_NOSIZE | self.SWP_NOACTIVATE,
            )
            self._set_alpha(255)

    def release(self) -> None:
        if not self._hwnd or not self.user32.IsWindow(self._hwnd):
            return
        self._set_alpha(255)
        if self._originally_hidden:
            self.user32.ShowWindow(self._hwnd, 0)
        elif self._originally_minimized:
            self.user32.ShowWindow(self._hwnd, self.SW_SHOWMINNOACTIVE)
        if self._foreground_owner and self.user32.IsWindow(self._foreground_owner):
            self.user32.SetForegroundWindow(self._foreground_owner)
        self._managed_hidden = False


class GatewayRuntime:
    """Drive Oopz's own visible client; this process never opens an Oopz socket."""

    def __init__(
        self,
        callbacks: GatewayCallbacks,
        backend_factory: Callable[[], CompanionBackend] = WindowsOopzBackend,
    ) -> None:
        self.callbacks = callbacks
        self._backend_factory = backend_factory
        self._commands: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._closed = False
        self._thread = threading.Thread(
            target=self._run,
            name="oopz-companion",
            daemon=True,
        )
        self._thread.start()

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        text = str(exc).strip() or exc.__class__.__name__
        return text if text.startswith(("Oopz", "请")) else f"Oopz：{text}"

    def _run(self) -> None:
        backend: CompanionBackend | None = None
        connected = False
        faulted = False
        current_channel = ""
        previous_ids: tuple[str, ...] = ()
        try:
            backend = self._backend_factory()
            open_thread = getattr(backend, "open_thread", None)
            if callable(open_thread):
                open_thread()
            while True:
                try:
                    command, payload = self._commands.get(timeout=0.35)
                except queue.Empty:
                    command, payload = "poll", None
                if command == "close":
                    return
                try:
                    if command == "connect":
                        backend.prepare()
                        connected = True
                        faulted = False
                        current_channel = ""
                        previous_ids = ()
                    elif command == "disconnect":
                        connected = False
                        current_channel = ""
                        previous_ids = ()
                        self.callbacks.status("已断开 Oopz", False)
                    elif command == "send":
                        if not connected:
                            raise OopzCompanionError("尚未连接 Oopz")
                        backend.send_message(str(payload))

                    if connected and command in {"connect", "send", "poll"}:
                        detected_channel = backend.current_channel()
                        if detected_channel != current_channel:
                            current_channel = detected_channel
                            previous_ids = ()
                            self.callbacks.channel(current_channel)
                        messages = backend.visible_messages()
                        if faulted or command == "connect":
                            faulted = False
                            self.callbacks.status(
                                f"已连接 Oopz · #{current_channel}", True
                            )
                        current_ids = tuple(item.message_id for item in messages)
                        if current_ids != previous_ids:
                            previous_ids = current_ids
                            self.callbacks.timeline(messages)
                except Exception as exc:
                    LOGGER.debug("Oopz companion operation failed", exc_info=exc)
                    if command == "poll":
                        if not faulted:
                            faulted = True
                            current_channel = ""
                            previous_ids = ()
                            self.callbacks.status("Oopz 已断开", False)
                            self.callbacks.channel("")
                            self.callbacks.error(self._friendly_error(exc))
                    else:
                        if command == "connect":
                            connected = False
                            current_channel = ""
                            self.callbacks.channel("")
                        self.callbacks.status("Oopz 未连接", False)
                        self.callbacks.error(self._friendly_error(exc))
        finally:
            if backend is not None:
                try:
                    backend.release()
                except Exception as exc:
                    LOGGER.debug("Oopz companion release failed", exc_info=exc)
                close_thread = getattr(backend, "close_thread", None)
                if callable(close_thread):
                    close_thread()

    def connect(self) -> None:
        self._commands.put(("connect", None))

    def disconnect(self) -> None:
        self._commands.put(("disconnect", None))

    def send(self, text: str) -> None:
        self._commands.put(("send", text))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._commands.put(("close", None))
        self._thread.join(timeout=8)
