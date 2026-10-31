"""Native/packaged interaction acceptance. Run in an interactive rinutm task.

Uses an isolated profile and its own focus target. Chat in native mode is fixture
traffic; packaged scrolling uses the app's existing adjustment samples.
Optional pywinauto/Pillow come from the existing probe environment, not the app.
"""
from __future__ import annotations

import ctypes
import hashlib
import struct
import json
import os
import re
import site
import subprocess
import sys
import time
import traceback
from ctypes import wintypes as W
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
site.addsitedir(str(Path.home() / 'typeslip-probe-venv/Lib/site-packages'))
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from oopz_overlay.adapters import win32
from oopz_overlay.core.settings import AppSettings, JsonSettingsStore
from oopz_overlay.adapters.session import WindowsDpapiProtector
from oopz_overlay.ui.tray import app_icon
from oopz_overlay.i18n import tr

MODE, OUT = sys.argv[1], Path(sys.argv[2])
assert MODE in {'native', 'packaged'}
os.environ['LOCALAPPDATA'] = str(OUT / (MODE + '-state'))
SHOTS = OUT / 'shots'
SHOTS.mkdir(exist_ok=True)
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
if MODE == 'native':
    app.setWindowIcon(app_icon())
from PIL import ImageGrab
sys.coinit_flags = 2
from pywinauto import Desktop
u = win32._user32()
u.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, W.DWORD, ctypes.c_size_t]
u.GetWindowRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
u.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
u.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
u.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
u.IsWindowVisible.argtypes = [W.HWND]
u.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
u.WindowFromPoint.argtypes = [W.POINT]
u.WindowFromPoint.restype = W.HWND
u.GetAncestor.argtypes = [W.HWND, W.UINT]
u.GetAncestor.restype = W.HWND
u.mouse_event.argtypes = [W.DWORD, W.DWORD, W.DWORD, W.DWORD, ctypes.c_size_t]
result = {'mode': MODE, 'checks': {}, 'fixture': 'native: synthetic chat; packaged: built-in adjustment samples'}
checks = result['checks']
controller = None
process = None
pid = None

def wait(ms=240):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(.01)


def until(fn, timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = fn()
        if value:
            return value
        wait(100)
    raise TimeoutError(str(fn))


def key(vk):
    u.keybd_event(vk, 0, 0, 0)
    u.keybd_event(vk, 0, 2, 0)
    wait()


def wheel(delta):
    u.mouse_event(0x0800, 0, 0, delta & 0xffffffff, 0)
    wait(300)


def rect(handle):
    r = W.RECT()
    assert u.GetWindowRect(handle, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def capture(handle, name):
    box = rect(handle)
    ImageGrab.grab(bbox=box, all_screens=True, include_layered_windows=True).save(SHOTS / (name + '.png'))
    return box


def windows(owner):
    found = []
    callback_type = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    @callback_type
    def each(handle, _):
        owner_id = W.DWORD()
        u.GetWindowThreadProcessId(handle, ctypes.byref(owner_id))
        if owner_id.value == owner and u.IsWindowVisible(handle):
            name, cls = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(handle, name, 256)
            u.GetClassNameW(handle, cls, 256)
            found.append((int(handle), name.value, cls.value))
        return True
    u.EnumWindows(each, 0)
    return found


def shell_click(item, button='left'):
    # Shell tooltips can cover the overflow icon itself; dismiss them without clicking.
    desktop = Desktop(backend='uia')
    bar = desktop.window(class_name='Shell_TrayWnd').rectangle()
    r = item.rectangle()
    panel = desktop.window(class_name='TopLevelWindowForOverflowXamlIsland')
    inside = panel.exists(timeout=.2) and u.IsWindowVisible(panel.handle) and panel.rectangle().left <= r.left < panel.rectangle().right and panel.rectangle().top <= r.top < panel.rectangle().bottom
    idle = panel.rectangle() if inside else bar
    u.SetCursorPos(idle.left + 4, idle.bottom - 4)
    wait(700)
    point = W.POINT((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    root = u.GetAncestor(u.WindowFromPoint(point), 2)
    cls = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(root, cls, 256)
    assert cls.value in {'Shell_TrayWnd', 'TopLevelWindowForOverflowXamlIsland'}, f'Tray coordinate is not on a visible Shell window: {cls.value}'
    u.SetCursorPos(point.x, point.y)
    down, up = (0x0008, 0x0010) if button == 'right' else (0x0002, 0x0004)
    u.mouse_event(down, 0, 0, 0, 0)
    u.mouse_event(up, 0, 0, 0, 0)
    wait()


def notification_icon():
    desktop = Desktop(backend='uia')
    for window in desktop.windows():
        if window.element_info.class_name != 'Windows.UI.Core.CoreWindow':
            continue
        for toast in window.descendants(control_type='Window'):
            if toast.element_info.automation_id == 'NormalToastView' and any(name in toast.element_info.name for name in ('TypeSlip', '纸条')):
                for button in toast.descendants(control_type='Button'):
                    if button.element_info.automation_id == 'DismissButton':
                        button.invoke()
                        wait(300)
    tray = desktop.window(class_name='Shell_TrayWnd')
    overflow = desktop.window(class_name='TopLevelWindowForOverflowXamlIsland')
    def overflow_visible():
        if not overflow.exists(timeout=.2) or not u.IsWindowVisible(overflow.handle):
            return False
        cloaked = W.DWORD()
        dwm = ctypes.WinDLL('dwmapi')
        dwm.DwmGetWindowAttribute.argtypes = [W.HWND, W.DWORD, ctypes.c_void_p, W.DWORD]
        assert dwm.DwmGetWindowAttribute(overflow.handle, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0
        return not cloaked.value
    if not overflow_visible():
        buttons = [x for x in tray.descendants(control_type='Button') if x.is_visible() and any(t in x.element_info.name for t in ('隐藏', 'hidden', 'Hidden', '溢出', 'overflow'))]
        if buttons:
            shell_click(buttons[0])
            until(overflow_visible)
    if overflow_visible():
        overflow.set_focus()
        wait(300)
    containers = [tray] + ([overflow] if overflow_visible() else [])
    for container in containers:
        for item in container.descendants():
            if 'TypeSlip ·' in item.element_info.name and item.is_visible():
                return item
    raise AssertionError('Visible TypeSlip notification icon not found')


def tray_menu(owner, command):
    shell_click(notification_icon(), button='right')
    wait()
    menu_handle = until(lambda: next((h for h, _, cls in windows(owner) if 'Popup' in cls), None))
    menu = Desktop(backend='win32').window(handle=menu_handle)
    r = menu.rectangle()
    assert 30 < r.height() < 130 and 40 < r.width() < 400
    menu.click_input(coords=(r.width() // 2, 12 if command == 'settings' else r.height() - 14))
    wait()


def target_focus():
    target.show()
    target.raise_()
    target.activateWindow()
    handle = int(target.winId())
    u.SetWindowPos(handle, win32.HWND_TOPMOST, 0, 0, 0, 0, win32.SWP_NOMOVE | win32.SWP_NOSIZE | win32.SWP_NOACTIVATE)
    left, top, right, bottom = rect(handle)
    u.SetCursorPos((left + right) // 2, (top + bottom) // 2)
    u.mouse_event(0x0002, 0, 0, 0, 0)
    u.mouse_event(0x0004, 0, 0, 0, 0)
    wait()
    result['focus-diagnostic'] = {'foreground': win32.foreground_window(), 'target': int(target.winId()), 'rect': rect(int(target.winId())), 'visible': bool(u.IsWindowVisible(int(target.winId())))}
    capture(int(target.winId()), 'focus-diagnostic')
    assert win32.foreground_window() == int(target.winId())


def native():
    global controller
    from oopz_overlay.app import AppController
    from oopz_overlay.core.timeline import ChatMessage
    c = controller = AppController(app)
    c.poll.stop()
    c.startup.stop()
    c.update_timer.stop()
    sent = []
    c.gateway.send = sent.append  # The only substituted boundary is network send.
    c.state = replace(c.state, connected=True, status='connected', settings=AppSettings(
        area_id='fixture', channel_id='fixture', channel_name='交互验收', overlay_width=420, overlay_height=240))
    c.hud.setGeometry(100, 80, 420, 240)
    c.timeline.merge([ChatMessage(str(i), 1775000000000000 + i * 1000000,
                                 'fixture', '队友 A', f'消息 {i:02d} / history line', False)
                      for i in range(80)], now=time.monotonic(), live=True)
    c.render()
    target_focus()
    handle = int(c.hud.winId())
    for exit_key, name in ((0x77, 'f8'), (0x0d, 'empty-enter'), (0x1b, 'escape')):
        key(0x77)
        until(lambda: c.state.mode == 'input' and win32.foreground_window() == handle)
        capture(handle, 'native-' + name + '-before')
        key(exit_key)
        until(lambda: c.state.mode == 'passive')
        assert c.state.mode == 'passive' and win32.foreground_window() == int(target.winId()) and sent == []
        capture(handle, 'native-' + name + '-after')
        checks[name] = True
    key(0x77)
    u.SetCursorPos(900, 500)  # Global wheel must work even away from the HUD.
    wheel(600)
    result['wheel-diagnostic'] = {'mode': c.state.mode, 'foreground': win32.foreground_window(), 'hud': handle, 'enabled': c.wheel_hook._enabled, 'hook': c.wheel_hook._hook, 'maximum': c.hud.messages.maximum_offset, 'offset': c.hud.messages.offset}
    assert c.hud.messages.offset > 0
    before_rect = c.hud.messages.geometry()
    capture(handle, 'native-scroll-button-visible')
    c.hud.latest.hide()
    wait()
    capture(handle, 'native-scroll-button-hidden')
    before = c.hud.messages.grab().toImage()
    assert c.hud.messages.geometry() == before_rect
    c.hud.latest.show()
    wait()
    after = c.hud.messages.grab().toImage()
    dpr = before.devicePixelRatio()
    width = int((c.hud.messages.width() - 12) * dpr)
    height = int((c.hud.messages.height() - c.hud.latest.height() - 12) * dpr)
    assert before.copy(0, 0, width, height) == after.copy(0, 0, width, height)
    checks['floating-button'] = {'message_rect': [before_rect.x(), before_rect.y(), before_rect.width(), before_rect.height()], 'text_pixels_identical': True}
    before = c.hud.messages.grab().toImage()
    c.timeline.merge([ChatMessage('80', 1775000080000000, 'b', 'Mika', '新消息到达', False)], now=time.monotonic(), live=True)
    c.render()
    wait()
    after = c.hud.messages.grab().toImage()
    assert before.copy(0, 0, width, before.height()) == after.copy(0, 0, width, after.height())
    capture(handle, 'native-history-new-message')
    checks['history-anchor-after-pruning'] = True
    c.hud.latest.click()
    wait()
    assert c.hud.messages.offset == 0 and app.focusWidget() is c.hud.input
    c.destinations = tuple(SimpleNamespace(area_id='fixture', area_name='验收', channel_id='fixture' + str(i), channel_name='频道' + str(i)) for i in range(2))
    c.render()
    key(0x09)
    until(lambda: c.state.mode == 'picker')
    key(0x28)
    key(0x0d)
    until(lambda: c.state.mode == 'input' and c.state.settings.channel_id == 'fixture1')
    checks['native-channel-keyboard-picker'] = True
    old_font = c.state.settings.font_size
    u.keybd_event(0x11, 0, 0, 0)
    wheel(120)
    u.keybd_event(0x11, 0, 2, 0)
    until(lambda: c.state.settings.font_size == old_font + 1)
    checks['native-control-wheel-font-size'] = True
    # Real Windows Chinese IME, including Enter while candidates are open.
    layouts = (ctypes.c_void_p * u.GetKeyboardLayoutList(0, None))()
    u.GetKeyboardLayoutList(len(layouts), layouts)
    chinese = next(x for x in layouts if x & 0xffff == 0x804)
    u.ActivateKeyboardLayout.argtypes = [ctypes.c_void_p, W.UINT]
    u.ActivateKeyboardLayout.restype = ctypes.c_void_p
    previous = u.ActivateKeyboardLayout(chinese, 0)
    try:
        imm = ctypes.WinDLL('imm32')
        imm.ImmGetContext.argtypes = [W.HWND]
        imm.ImmGetContext.restype = W.HANDLE
        context = imm.ImmGetContext(handle)
        imm.ImmSetOpenStatus.argtypes = [W.HANDLE, W.BOOL]
        imm.ImmSetConversionStatus.argtypes = [W.HANDLE, W.DWORD, W.DWORD]
        imm.ImmSetOpenStatus(context, True)
        imm.ImmSetConversionStatus(context, 1, 0)
        imm.ImmReleaseContext.argtypes = [W.HWND, W.HANDLE]
        imm.ImmReleaseContext(handle, context)
        for letter in 'NIHAO':
            key(ord(letter))
        capture(handle, 'native-ime-composing')
        until(lambda: c.hud._composing)
        assert not sent
        key(0x0d)
        assert c.state.mode == 'input' and not sent
        assert c.hud.input.text()
        entered = c.hud.input.text()
        c.hud.input.clear()
        for letter in 'NIHAO':
            key(ord(letter))
        key(0x20)  # Microsoft Pinyin chooses a Chinese candidate with Space.
        assert any('\u4e00' <= ch <= '\u9fff' for ch in c.hud.input.text())
        capture(handle, 'native-ime-committed')
        key(0x0d)
        assert c.state.mode == 'passive' and len(sent) == 1
        checks['real-chinese-ime-enter'] = {'sent': sent[:], 'first-enter-committed': entered, 'candidate-enter-did-not-send': True}
    finally:
        u.ActivateKeyboardLayout(previous, 0)
    key(0x77)
    target_focus()
    assert c.state.mode == 'passive'
    checks['blur-does-not-steal-focus'] = True
    key(0x78)
    assert not c.hud.isVisible()
    key(0x78)
    assert c.hud.isVisible()
    checks['f9'] = True
    c.shutdown()
    controller = None


def packaged():
    global process, pid
    profile = OUT / 'packaged-profile'
    assert not profile.exists(), 'Use a fresh isolated packaged-profile'
    settings = AppSettings(channel_id='fixture', channel_name='交互验收', font_size=20,
                           overlay_width=260, overlay_height=135,
                           position_x=.25, position_y=.3, notification_sound='')
    store = JsonSettingsStore(profile / 'RinChan/OopzTacticalOverlay/state.bin', WindowsDpapiProtector())
    store.save(settings)
    env = os.environ.copy()
    env['LOCALAPPDATA'] = str(profile)
    env.pop('QT_QPA_PLATFORM', None)
    env['HTTPS_PROXY'] = env['HTTP_PROXY'] = 'http://127.0.0.1:9'
    executable = ROOT / 'release/OopzTacticalOverlay.exe'
    import win32api
    version = win32api.GetFileVersionInfo(str(executable), '\\')
    assert (version['FileVersionMS'], version['FileVersionLS']) == (1 << 16, 2 << 16)
    library = win32api.LoadLibraryEx(str(executable), 0, 2)
    try:
        groups = win32api.EnumResourceNames(library, 14)
        data = win32api.LoadResource(library, 14, groups[0])
        assert struct.unpack_from('<HHH', data) == (0, 1, 8)
        sizes = sorted((struct.unpack_from('<B', data, 6 + 14 * i)[0] or 256) for i in range(8))
        assert sizes == [16, 20, 24, 32, 48, 64, 128, 256]
        checks['exe-version-and-eight-icon-resources'] = {'version': '1.0.2.0', 'icon_sizes': sizes, 'sha256': hashlib.sha256(executable.read_bytes()).hexdigest()}
    finally:
        win32api.FreeLibrary(library)
    process = subprocess.Popen([str(executable)], env=env)
    log = profile / 'RinChan/OopzTacticalOverlay/startup.log'
    line = until(lambda: log.read_text(encoding='utf-8') if log.exists() else '', 90)
    pid = int(re.search(r'pid=(\d+) START', line)[1])
    handle = until(lambda: next((h for h, _, cls in windows(pid) if 'QWindowTool' in cls), None), 90)
    wait(1200)
    target_focus()
    def input_visible():
        return any(x.is_visible() for x in Desktop(backend='uia').window(handle=handle).descendants(control_type='Edit'))
    for exit_key, name in ((0x77, 'f8'), (0x0d, 'empty-enter'), (0x1b, 'escape')):
        key(0x77)
        until(lambda: input_visible() and win32.foreground_window() == handle)
        capture(handle, 'exe-' + name + '-before')
        key(exit_key)
        until(lambda: not input_visible())
        assert win32.foreground_window() == int(target.winId())
        capture(handle, 'exe-' + name + '-after')
        checks[name] = True
    key(0x78)
    assert not u.IsWindowVisible(handle)
    key(0x78)
    assert u.IsWindowVisible(handle)
    checks['f9'] = True
    backdrop.activateWindow()
    target.hide()
    tray_menu(pid, 'settings')
    settings_handle = until(lambda: next((h for h, title, _ in windows(pid) if title == '纸条设置'), None))
    capture(settings_handle, 'exe-settings-new-icon')
    # Capture only the taskbar strip and the owned notification icon.
    taskbar = Desktop(backend='uia').window(class_name='Shell_TrayWnd')
    r = taskbar.rectangle()
    ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom), all_screens=True, include_layered_windows=True).save(SHOTS / 'exe-taskbar-icon.png')
    buttons = [x for x in taskbar.descendants(control_type='Button') if tr('app') in x.element_info.name and 'SystemTray' not in x.element_info.class_name and '·' not in x.element_info.name]
    assert buttons, 'Owned settings taskbar button not found'
    r = buttons[0].rectangle()
    ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom), all_screens=True, include_layered_windows=True).save(SHOTS / 'exe-taskbar-icon-detail.png')
    icon = notification_icon()
    panel = Desktop(backend='uia').window(class_name='TopLevelWindowForOverflowXamlIsland')
    idle = panel.rectangle()
    u.SetCursorPos(idle.left + 4, idle.bottom - 4)
    wait(700)
    r = icon.rectangle()
    ImageGrab.grab(bbox=(r.left - 8, r.top - 8, r.right + 8, r.bottom + 8), all_screens=True, include_layered_windows=True).save(SHOTS / 'exe-tray-icon.png')
    u.SetForegroundWindow(settings_handle)
    wait()
    sw = Desktop(backend='uia').window(handle=settings_handle)
    sw.set_focus()
    adjust = next(x for x in sw.descendants(control_type='Button') if x.element_info.name == '调整位置与大小')
    adjust.click_input()
    wait()
    bounds = capture(handle, 'exe-scroll-latest')
    def hint_bounds():
        hint = next(x for x in Desktop(backend='uia').window(handle=handle).descendants(control_type='Text') if x.element_info.name == tr('adjust_hint'))
        r = hint.rectangle()
        return (r.left, r.top, r.right, r.bottom)
    message_bottom = hint_bounds()
    def latest_button():
        return next((x for x in Desktop(backend='uia').window(handle=handle).descendants(control_type='Button') if '最新' in x.element_info.name and x.is_visible()), None)
    u.SetCursorPos(900, 500)
    wheel(120)
    button = until(latest_button)
    assert hint_bounds() == message_bottom
    assert button.rectangle().bottom < message_bottom[1], 'Latest must float above the hint, inside the message area'
    assert rect(handle) == bounds
    capture(handle, 'exe-scroll-history')
    wheel(120)
    capture(handle, 'exe-scroll-history-further')
    assert rect(handle) == bounds
    latest_button().click_input()
    until(lambda: latest_button() is None)
    assert rect(handle) == bounds
    capture(handle, 'exe-scroll-returned')
    assert hint_bounds() == message_bottom
    from PIL import Image, ImageChops
    before = Image.open(SHOTS / 'exe-scroll-latest.png').convert('RGB')
    after = Image.open(SHOTS / 'exe-scroll-returned.png').convert('RGB')
    assert ImageChops.difference(before, after).getbbox() is None
    checks['floating-scroll-native-exe'] = {'hud_rect_unchanged': bounds, 'message_boundary_unchanged': message_bottom, 'button_inside_message_area': True, 'roundtrip_pixels_identical': True, 'button_shown_and_hidden': True, 'source_pixel_proof': 'native floating-button'}
    key(0x1b)
    until(lambda: u.IsWindowVisible(settings_handle))
    tray_menu(pid, 'quit')
    process.wait(timeout=30)
    until(lambda: 'EXIT code=0' in log.read_text(encoding='utf-8'))
    assert 'UNHANDLED' not in log.read_text(encoding='utf-8')
    checks['tray-settings-and-graceful-quit'] = True
    process = None
    released = []
    for ident, vk in ((0xc201, 0x77), (0xc202, 0x78)):
        ok = bool(u.RegisterHotKey(None, ident, 0x4000, vk))
        released.append(ok)
        if ok:
            u.UnregisterHotKey(None, ident)
    assert all(released)
    checks['hotkeys-released'] = True


backdrop = QWidget(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
backdrop.setWindowTitle('TypeSlip owned screenshot backdrop')
backdrop.setGeometry(20, 20, 620, 740)
backdrop.setStyleSheet('background:#243142;')
backdrop.show()

target = QWidget()
target.setWindowTitle('TypeSlip 1.0.2 focus test target')
target.setGeometry(680, 140, 360, 180)
layout = QVBoxLayout(target)
layout.addWidget(QLabel('TypeSlip 1.0.2 — owned focus test target'))
target.show()
try:
    (native if MODE == 'native' else packaged)()
    result['passed'] = True
except BaseException:
    result['error'] = traceback.format_exc()
    raise
finally:
    if controller:
        controller.shutdown()
    if process and process.poll() is None and pid:
        try:
            tray_menu(pid, 'quit')
            process.wait(timeout=20)
        except Exception:
            result['cleanup_error'] = traceback.format_exc()
    target.close()
    backdrop.close()
    (OUT / (MODE + '-result.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
