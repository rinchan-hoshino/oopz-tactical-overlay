"""Native desktop regression, using only disposable windows and fake chat data.

Run on a dedicated Windows test desktop, never on the user's active game session.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
import time
import traceback
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QVBoxLayout, QWidget

from oopz_overlay.chat import ChatMessage
from oopz_overlay.settings import AppSettings
from oopz_overlay.settings_dialog import SetupDialog
from oopz_overlay.widgets import OverlayWindow
from oopz_overlay.win32_input import (
    GlobalHotkeyRegistration,
    GlobalWheelRegistration,
    _user32,
)


class Placement(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.UINT),
        ("flags", wintypes.UINT),
        ("showCmd", wintypes.UINT),
        ("min", wintypes.POINT),
        ("max", wintypes.POINT),
        ("normal", wintypes.RECT),
    ]


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def target(app: QApplication, output: Path) -> int:
    window = QWidget()
    window.setWindowTitle("Oopz validation target — disposable")
    window.setGeometry(90, 90, 640, 360)
    layout = QVBoxLayout(window)
    layout.addWidget(
        QLabel("Disposable test window. No game or Oopz account is connected.")
    )
    field = QLineEdit()
    layout.addWidget(field)
    window.show()
    window.activateWindow()
    field.setFocus()
    app.processEvents()
    write_json(output, {"hwnd": int(window.winId())})
    QTimer.singleShot(120000, app.quit)
    return app.exec()


def probe(app: QApplication, output: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    target_info = output / "target.json"
    target_info.unlink(missing_ok=True)
    result = {"passed": False, "cycles": 0, "checks": [], "network": "not used"}
    process = subprocess.Popen([sys.executable, __file__, "--target", str(target_info)])
    overlay = None
    keys = None
    wheel = None
    user32 = _user32()
    user32.GetWindowPlacement.argtypes = [wintypes.HWND, ctypes.POINTER(Placement)]
    user32.GetWindowPlacement.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.keybd_event.argtypes = [
        wintypes.BYTE,
        wintypes.BYTE,
        wintypes.DWORD,
        ctypes.c_size_t,
    ]
    user32.mouse_event.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_size_t,
    ]

    def placement(hwnd):
        value = Placement()
        value.length = ctypes.sizeof(value)
        assert user32.GetWindowPlacement(hwnd, ctypes.byref(value))
        return {
            "mode": int(value.showCmd),
            "rect": [
                value.normal.left,
                value.normal.top,
                value.normal.right,
                value.normal.bottom,
            ],
            "flags": int(value.flags),
        }

    def key(vk):
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)
        QTest.qWait(180)

    try:
        deadline = time.monotonic() + 20
        while not target_info.exists() and time.monotonic() < deadline:
            QTest.qWait(50)
        assert target_info.exists(), "target window did not start"
        hwnd = json.loads(target_info.read_text(encoding="utf-8"))["hwnd"]
        overlay = OverlayWindow()
        overlay.configure(AppSettings())
        overlay.set_connection_status("#验证频道", True)
        overlay.merge_messages(
            [
                ChatMessage(str(i), i + 1, "peer", "队友", f"验证消息 {i}", False)
                for i in range(30)
            ]
        )
        sent = []
        overlay.send_requested.connect(sent.append)
        keys = GlobalHotkeyRegistration(int(overlay.winId()))
        keys.configure("F8", "F9")
        overlay.activation_hotkey_pressed.connect(overlay.show_overlay)
        overlay.visibility_hotkey_pressed.connect(overlay.toggle_visibility)

        class Bridge(QObject):
            delta = Signal(int)

        bridge = Bridge()
        received_wheel = []
        bridge.delta.connect(lambda delta: received_wheel.append(delta))
        bridge.delta.connect(overlay.handle_global_wheel)
        hook_errors = []
        wheel = GlobalWheelRegistration(
            bridge.delta.emit,
            window_id=int(overlay.winId()),
            on_error=hook_errors.append,
        )
        overlay.interaction_changed.connect(wheel.set_enabled)
        for mode in (1, 3):
            user32.ShowWindow(hwnd, mode)
            user32.SetForegroundWindow(hwnd)
            QTest.qWait(180)
            assert int(user32.GetForegroundWindow() or 0) == hwnd, (
                "test desktop did not grant foreground"
            )
            before = placement(hwnd)
            for cycle in range(8):
                key(0x77)
                assert overlay.is_active, "F8 did not activate"
                assert int(user32.GetForegroundWindow() or 0) == int(overlay.winId()), (
                    "HUD not foreground"
                )
                if mode == 1 and cycle == 0:
                    scroll = overlay.history.verticalScrollBar()
                    previous = scroll.value()
                    user32.mouse_event(0x0800, 0, 0, 120, 0)
                    QTest.qWait(250)
                    result["wheel_probe"] = {
                        "before": previous,
                        "after": scroll.value(),
                        "maximum": scroll.maximum(),
                        "received": list(received_wheel),
                        "hook": wheel._hook,
                        "thread_alive": wheel._thread.is_alive(),
                        "foreground": int(user32.GetForegroundWindow() or 0),
                        "overlay_hwnd": int(overlay.winId()),
                        "hook_errors": hook_errors,
                    }
                    assert scroll.value() < previous and received_wheel, (
                        "global wheel not delivered"
                    )
                    overlay.grab().save(str(output / "hud-windows.png"))
                QTest.keyClicks(overlay.input, "native input")
                key(0x0D if cycle % 2 == 0 else 0x1B)
                assert not overlay.is_active, "input did not close"
                assert int(user32.GetForegroundWindow() or 0) == hwnd, (
                    "focus did not return"
                )
                assert placement(hwnd) == before, "target placement changed"
                assert not wheel._enabled and not wheel._hook, (
                    "passive mouse hook is still installed"
                )
                result["cycles"] += 1
            result["checks"].append(f"placement-and-focus-mode-{mode}")

        key(0x77)
        user32.SetForegroundWindow(hwnd)
        QTest.qWait(200)
        assert not overlay.is_active and not wheel._enabled, (
            "outside focus did not cancel capture"
        )
        wheel_count = len(received_wheel)
        user32.mouse_event(0x0800, 0, 0, 120, 0)
        QTest.qWait(200)
        assert len(received_wheel) == wheel_count, "passive HUD consumed scrolling"
        result["checks"].extend(
            ["outside-focus-cancels-input", "passive-wheel-passes-through"]
        )
        assert len(sent) == 8, "Enter/Escape submission count differs"
        result["sent_to_fixture"] = len(sent)
        key(0x78)
        assert not overlay.isVisible(), "F9 did not hide the HUD"
        assert int(user32.GetForegroundWindow() or 0) == hwnd
        key(0x78)
        assert overlay.isVisible() and not overlay.is_active, (
            "F9 did not restore the passive HUD"
        )
        assert int(user32.GetForegroundWindow() or 0) == hwnd
        result["checks"].append("visibility-hotkey-preserves-focus")

        dialog = SetupDialog(
            AppSettings(
                area_id="demo",
                area_name="猫尾服务器",
                channel_id="demo",
                channel_name="塔科夫",
            )
        )
        dialog.set_connection_status("#塔科夫", True)
        dialog.show()
        app.processEvents()
        dialog.grab().save(str(output / "settings-windows.png"))
        dialog.close()
        result["passed"] = True
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        if keys is not None:
            keys.close()
        if wheel is not None:
            wheel.close()
        if overlay is not None:
            overlay.hide()
        process.terminate()
        process.wait(timeout=10)
        write_json(output / "result.json", result)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    raise SystemExit(
        target(app, args.target) if args.target else probe(app, args.output)
    )
