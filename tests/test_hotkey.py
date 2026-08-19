import pytest

from oopz_overlay.win32_input import (
    VK_RETURN,
    GlobalHotkeyMonitor,
    HotkeySpec,
    parse_hotkey,
)


def test_parse_hotkey_supports_plain_enter_and_modified_function_key() -> None:
    assert parse_hotkey("Enter") == HotkeySpec(key=VK_RETURN)
    assert parse_hotkey("Ctrl + Alt + F8") == HotkeySpec(
        key=0x77,
        ctrl=True,
        alt=True,
    )


def test_global_monitor_edges_key_state_without_any_process_match() -> None:
    class User32:
        def __init__(self) -> None:
            self.down: set[int] = set()

        def GetAsyncKeyState(self, key: int) -> int:
            return 0x8000 if key in self.down else 0

    monitor = object.__new__(GlobalHotkeyMonitor)
    monitor._states = {}
    monitor._specs = {}
    monitor._user32 = User32()

    monitor._user32.down = {0x77}
    assert monitor.hotkey_pressed("F8")
    assert not monitor.hotkey_pressed("F8")
    assert not monitor.hotkey_pressed("F9")
    monitor._user32.down = set()
    assert not monitor.hotkey_pressed("F8")
    monitor._user32.down = {0x77}
    assert monitor.hotkey_pressed("F8")

    monitor._user32.down = {0x78}
    assert monitor.hotkey_pressed("F9")
    assert not monitor.hotkey_pressed("F9")


def test_parse_hotkey_normalizes_letters_and_rejects_ambiguous_sequences() -> None:
    assert parse_hotkey("Shift+q") == HotkeySpec(key=ord("Q"), shift=True)

    with pytest.raises(ValueError, match="只能包含一个主按键"):
        parse_hotkey("A+B")
    assert parse_hotkey("Ctrl+Delete") == HotkeySpec(key=0x2E, ctrl=True)

    with pytest.raises(ValueError, match="支持"):
        parse_hotkey("Ctrl+BrowserBack")
