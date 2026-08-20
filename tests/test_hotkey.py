import pytest

from oopz_overlay.win32_input import (
    HOTKEY_ACTIVATE_ID,
    HOTKEY_VISIBILITY_ID,
    HWND_TOPMOST,
    MOD_CONTROL,
    MOD_NOREPEAT,
    VK_RETURN,
    GlobalHotkeyRegistration,
    GlobalWheelRegistration,
    HotkeySpec,
    _focus_window_native,
    _restore_window_native,
    parse_hotkey,
)


def test_parse_hotkey_supports_plain_enter_and_modified_function_key() -> None:
    assert parse_hotkey("Enter") == HotkeySpec(key=VK_RETURN)
    assert parse_hotkey("Ctrl + Alt + F8") == HotkeySpec(
        key=0x77,
        ctrl=True,
        alt=True,
    )


def test_global_hotkeys_are_registered_with_windows_and_can_be_reconfigured() -> None:
    class User32:
        def __init__(self) -> None:
            self.registered: dict[int, tuple[int, int]] = {}
            self.unregistered: list[int] = []

        def RegisterHotKey(
            self, _window: int, identifier: int, modifiers: int, key: int
        ) -> int:
            self.registered[identifier] = (modifiers, key)
            return 1

        def UnregisterHotKey(self, _window: int, identifier: int) -> int:
            self.unregistered.append(identifier)
            self.registered.pop(identifier, None)
            return 1

    user32 = User32()
    registration = GlobalHotkeyRegistration(123, user32=user32)

    registration.configure("F8", "Ctrl+F9")

    assert user32.registered[HOTKEY_ACTIVATE_ID] == (MOD_NOREPEAT, 0x77)
    assert user32.registered[HOTKEY_VISIBILITY_ID] == (
        MOD_NOREPEAT | MOD_CONTROL,
        0x78,
    )

    registration.configure("F10", "Ctrl+F11")
    assert user32.unregistered == [HOTKEY_ACTIVATE_ID, HOTKEY_VISIBILITY_ID]
    registration.close()
    assert user32.registered == {}


def test_global_wheel_hook_only_consumes_vertical_wheel_while_enabled() -> None:
    received: list[int] = []
    registration = GlobalWheelRegistration(
        lambda delta: received.append(delta),
        user32=None,
        kernel32=None,
        install=False,
    )

    assert not registration.dispatch(0x020A, 120 << 16)
    registration.set_enabled(True)
    assert registration.dispatch(0x020A, 120 << 16)
    assert registration.dispatch(0x020A, ((-120) & 0xFFFF) << 16)
    assert not registration.dispatch(0x020E, 120 << 16)
    assert received == [120, -120]


def test_focus_window_reasserts_topmost_and_forces_one_retry() -> None:
    class User32:
        def __init__(self) -> None:
            self.foreground = 900
            self.topmost_target = None
            self.switched = False

        def GetForegroundWindow(self) -> int:
            return self.foreground

        def GetWindowThreadProcessId(self, _window: int, _process) -> int:
            return 8

        def AttachThreadInput(self, *_args) -> int:
            return 1

        def ShowWindow(self, *_args) -> int:
            return 1

        def SetWindowPos(self, window: int, insert_after: int, *_args) -> int:
            self.topmost_target = (window, insert_after)
            return 1

        def BringWindowToTop(self, *_args) -> int:
            return 1

        def SetForegroundWindow(self, window: int) -> int:
            if self.switched:
                self.foreground = window
            return 1

        def SetActiveWindow(self, *_args) -> int:
            return 1

        def SetFocus(self, *_args) -> int:
            return 1

        def SwitchToThisWindow(self, window: int, _alt_tab: bool) -> None:
            self.switched = True
            self.foreground = window

    class Kernel32:
        @staticmethod
        def GetCurrentThreadId() -> int:
            return 9

    user32 = User32()

    assert _focus_window_native(user32, Kernel32(), 100, 101)
    assert user32.topmost_target == (100, HWND_TOPMOST)
    assert user32.foreground == 100


def test_restore_window_returns_to_previous_foreground_without_making_it_topmost() -> (
    None
):
    class User32:
        def __init__(self) -> None:
            self.foreground = 100
            self.topmost_calls = 0
            self.show_calls = 0

        @staticmethod
        def IsWindow(window: int) -> int:
            return int(window == 900)

        def GetForegroundWindow(self) -> int:
            return self.foreground

        @staticmethod
        def GetWindowThreadProcessId(_window: int, _process) -> int:
            return 8

        @staticmethod
        def AttachThreadInput(*_args) -> int:
            return 1

        @staticmethod
        def IsIconic(_window: int) -> int:
            return 0

        def ShowWindow(self, *_args) -> int:
            self.show_calls += 1
            return 1

        @staticmethod
        def BringWindowToTop(*_args) -> int:
            return 1

        def SetForegroundWindow(self, window: int) -> int:
            self.foreground = window
            return 1

        @staticmethod
        def SetActiveWindow(*_args) -> int:
            return 1

        def SetWindowPos(self, *_args) -> int:
            self.topmost_calls += 1
            return 1

    class Kernel32:
        @staticmethod
        def GetCurrentThreadId() -> int:
            return 9

    user32 = User32()

    assert _restore_window_native(user32, Kernel32(), 900)
    assert user32.foreground == 900
    assert user32.show_calls == 0
    assert user32.topmost_calls == 0


def test_parse_hotkey_normalizes_letters_and_rejects_ambiguous_sequences() -> None:
    assert parse_hotkey("Shift+q") == HotkeySpec(key=ord("Q"), shift=True)

    with pytest.raises(ValueError, match="只能包含一个主按键"):
        parse_hotkey("A+B")
    assert parse_hotkey("Ctrl+Delete") == HotkeySpec(key=0x2E, ctrl=True)

    with pytest.raises(ValueError, match="支持"):
        parse_hotkey("Ctrl+BrowserBack")
