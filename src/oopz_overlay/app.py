"""Composition root: external events enter through queued signals on the GUI thread."""
from __future__ import annotations
import os
import sys
import threading
from dataclasses import replace
from pathlib import Path
from time import monotonic
from PySide6.QtCore import QObject, Signal, QTimer, QLockFile, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication
from . import __version__
from .core.settings import AppSettings, JsonSettingsStore
from .core.state import AppState, reduce
from .core.timeline import Timeline
from .adapters.oopz import GatewayRuntime, GatewayCallbacks
from .adapters.session import WindowsDpapiProtector
from .adapters import win32, updater
from .ui.hud import Hud, sample_timeline
from .ui.settings_window import SettingsWindow
from .ui.tray import Tray, app_icon
from .i18n import tr

def state_root() -> Path:
    return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'RinChan' / 'OopzTacticalOverlay'

class SingleInstance(QObject):
    activated = Signal()

    def __init__(self, root):
        super().__init__()
        root.mkdir(parents=True, exist_ok=True)
        self.name = win32.instance_name(root)
        self.lock = QLockFile(str(root / 'application.lock'))
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._connected)

    def acquire(self):
        if not self.lock.tryLock(0):
            client = QLocalSocket(self)
            client.connectToServer(self.name)
            if client.waitForConnected(1000):
                client.write(b'settings')
                client.waitForBytesWritten(1000)
                client.disconnectFromServer()
            return False
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            self.lock.unlock()
            raise OSError('Cannot create application entry')
        return True

    def _connected(self):
        while self.server.hasPendingConnections():
            client = self.server.nextPendingConnection()
            client.disconnected.connect(client.deleteLater)
            client.readyRead.connect(lambda c=client: c.readAll())
            self.activated.emit()

    def close(self):
        self.server.close()
        self.lock.unlock()

class Bridge(QObject):
    gateway = Signal(object)
    login = Signal(object)
    update = Signal(object)
    wheel = Signal(int, bool)
    input_error = Signal(str)

class AppController(QObject):

    def __init__(self, application):
        super().__init__()
        self.application = application
        application.setQuitOnLastWindowClosed(False)
        self.root = state_root()
        self.store = JsonSettingsStore(self.root / 'state.bin', WindowsDpapiProtector())
        self._load_error = False
        try:
            settings = self.store.load()
        except (OSError, ValueError, TypeError, UnicodeError):
            settings = AppSettings()
            self._load_error = True
        self.state = AppState(settings=settings)
        self.timeline = Timeline()
        self.destinations = ()
        self._return_window = 0
        self._closing = False
        self._reading = False
        self._inspection = False
        self._serial = 0
        self._retry = False
        self._update_status = tr('checking')
        self.settings_window = None
        self.bridge = Bridge()
        self.bridge.gateway.connect(self.gateway_event, Qt.ConnectionType.QueuedConnection)
        self.bridge.login.connect(self.login_result, Qt.ConnectionType.QueuedConnection)
        self.bridge.update.connect(self.update_progress, Qt.ConnectionType.QueuedConnection)
        self.bridge.wheel.connect(self.wheel, Qt.ConnectionType.QueuedConnection)
        self.bridge.input_error.connect(lambda _: self.notice('focus_failed'), Qt.ConnectionType.QueuedConnection)
        noop = lambda *args: None
        self.gateway = GatewayRuntime(GatewayCallbacks(noop, noop, noop, noop, noop, event=self.bridge.gateway.emit))
        self.hud = Hud()
        self.hud.action.connect(self.action)
        self.hotkeys = None
        self.wheel_hook = None
        if os.name == 'nt':
            self.hotkeys = win32.GlobalHotkeyRegistration(int(self.hud.winId()))
            try:
                self.hotkeys.configure(settings.hotkey, settings.visibility_hotkey)
            except (OSError, ValueError):
                self.state = reduce(self.state, 'status', 'hotkey_failed')
            self.wheel_hook = win32.GlobalWheelRegistration(self._native_wheel, window_id=int(self.hud.winId()), on_error=self.bridge.input_error.emit)
        self.tray = Tray(self)
        self.tray.toggle.connect(lambda: self.action('toggle'))
        self.tray.settings_requested.connect(self.open_settings)
        self.tray.quit_requested.connect(self.shutdown)
        self.tray.show()
        self._place()
        self._sample = sample_timeline()
        self.render()
        self.poll = QTimer(self)
        self.poll.setInterval(5000)
        self.poll.timeout.connect(self.read_session)
        self.poll.start()
        self.startup = QTimer(self)
        self.startup.setSingleShot(True)
        self.startup.timeout.connect(self.read_session)
        self.startup.start(0)
        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self.check_update)
        self.update_timer.start(1800)
        if self._load_error:
            self.notice('settings_failed')

    def render(self):
        state = self.state
        self.hud.render(state, self._sample if state.mode == 'adjust' else self.timeline, self.destinations)
        settings_open = self.settings_window is not None and self.settings_window.isVisible()
        self.hud.setVisible(state.visible and not settings_open)
        if self.wheel_hook:
            self.wheel_hook.set_enabled(state.mode != 'passive')
        self.tray.render(self.state)

    def _place(self):
        s = self.state.settings
        screen = next((screen for screen in QGuiApplication.screens() if screen.name() == s.screen_name), self.hud.screen())
        area = screen.availableGeometry()
        width = max(260, min(s.overlay_width or min(360, max(260, int(area.width() * 0.21))), area.width()))
        height = max(135, min(s.overlay_height or min(165, max(135, int(area.height() * 0.2))), area.height()))
        self.hud.resize(width, height)
        self.hud.move(max(area.left(), min(area.right() - width + 1, area.left() + round(area.width() * s.position_x) - width // 2)), max(area.top(), min(area.bottom() - height + 1, area.top() + round(area.height() * s.position_y) - height // 2)))

    def action(self, kind, value=None):
        if self._closing:
            return
        if kind == 'activate':
            if self.state.mode != 'passive':
                self.action('cancel')
                return
            if self.settings_window:
                self.settings_window.hide()
            self._return_window = win32.foreground_window()
            self.state = reduce(self.state, 'activate')
            self.timeline.mark_read()
            self.render()
            self.hud.raise_()
            self.hud.activateWindow()
            widget = self.hud.picker if self.state.mode == 'picker' else self.hud.input
            widget.setFocus(Qt.FocusReason.ShortcutFocusReason)
            if os.name == 'nt':
                if not win32.focus_window(int(self.hud.winId()), int(self.hud.winId())):
                    self.state = reduce(self.state, 'cancel')
                    self.notice('focus_failed')
                else:
                    win32.prepare_input_method(int(self.hud.winId()))
            if self.state.mode == 'picker':
                self.list_channels()
        elif kind == 'adjust':
            self._return_window = win32.foreground_window()
            if self.settings_window:
                self.settings_window.hide()
            self.state = replace(self.state, mode='adjust', visible=True)
            self.render()
            self.hud.raise_()
            self.hud.activateWindow()
            self.hud.messages.setFocus()
            if os.name == 'nt':
                win32.focus_window(int(self.hud.winId()), int(self.hud.winId()))
        elif kind in {'cancel', 'blur', 'toggle'}:
            adjusting = self.state.mode == 'adjust'
            active = self.state.mode != 'passive'
            self.state = reduce(self.state, 'toggle' if kind == 'toggle' else 'cancel')
            if active and kind != 'blur':
                self.restore_focus()
            if adjusting and self.settings_window:
                self.settings_window.show()
                if kind != 'blur':
                    self.settings_window.raise_()
                    self.settings_window.activateWindow()
        elif kind == 'draft':
            self.state = reduce(self.state, 'draft', value)
        elif kind == 'send':
            if not value.strip():
                return
            if not self.state.connected:
                self.state = reduce(self.state, 'draft', value)
                self.state = reduce(self.state, 'cancel')
                self.notice('send_failed')
            else:
                self.gateway.send(value)
                self.state = reduce(self.state, 'submit')
            self.restore_focus()
        elif kind == 'picker':
            self.state = reduce(self.state, 'picker')
            self.list_channels()
        elif kind == 'channel':
            self.configure(replace(self.state.settings, area_id=value.area_id, area_name=value.area_name, channel_id=value.channel_id, channel_name=value.channel_name))
            self.state = reduce(self.state, 'input')
            self.connect_current(clear=True)
        elif kind == 'font_size':
            self.configure(replace(self.state.settings, font_size=value))
        elif kind == 'geometry':
            screen = self.hud.screen()
            area = screen.availableGeometry()
            center = value.center()
            self.configure(replace(self.state.settings, screen_name=screen.name(), position_x=max(0, min(1, (center.x() - area.left()) / area.width())), position_y=max(0, min(1, (center.y() - area.top()) / area.height())), overlay_width=value.width(), overlay_height=value.height()))
        self.render()

    def restore_focus(self):
        if self._return_window:
            win32.restore_window(self._return_window, expected_foreground=int(self.hud.winId()))
        self._return_window = 0

    def _native_wheel(self, delta):
        self.bridge.wheel.emit(delta, win32.control_pressed())

    def wheel(self, delta, control):
        self.hud.handle_wheel(delta, control)

    def configure(self, settings):
        try:
            if self.hotkeys:
                self.hotkeys.configure(settings.hotkey, settings.visibility_hotkey)
        except (OSError, ValueError):
            if self.settings_window:
                self.settings_window.sync(self.state.settings)
            self.notice('hotkey_failed')
            return
        self.state = reduce(self.state, 'settings', settings)
        if not self._load_error:
            try:
                self.store.save(settings)
            except OSError:
                self.notice('save_failed')
        if self.settings_window:
            self.settings_window.sync(settings)
        self.render()

    def read_session(self):
        if self._closing or self._reading:
            return
        self._reading = True
        self.gateway.check_session()

    def session_checked(self, session):
        self._reading = False
        if session is None:
            self._serial += 1
            self._inspection = False
            self.gateway.disconnect()
            self.destinations = ()
            self.timeline = Timeline()
            self.state = reduce(self.state, 'logout', self.gateway.generation)
            self.render()
            return
        old = self.state.settings
        changed = (old.person_uid, old.jwt_token, old.device_id) != (session.person_uid, session.jwt_token, session.device_id)
        if changed:
            self.gateway.disconnect()
            self.timeline = Timeline()
            self._serial += 1
            self._inspection = False
            self.state = reduce(self.state, 'settings', replace(old, person_uid=session.person_uid, jwt_token=session.jwt_token, device_id=session.device_id, app_version=session.app_version))
            self.state = reduce(self.state, 'connection', self.gateway.generation)
            self.list_channels()
        elif self._retry:
            self.connect_current(clear=False)
        elif self.state.status in {'login', 'connecting'} and (not self._inspection):
            self.list_channels()
        self.render()

    def list_channels(self):
        if self._inspection or not self.state.settings.has_credentials:
            return
        self._inspection = True
        self._serial += 1
        serial = self._serial
        self.gateway.list_channels(self.state.settings, success=lambda result: self.bridge.login.emit((serial, result)))

    def login_result(self, event):
        serial, result = event
        if self._closing or serial != self._serial:
            return
        self._inspection = False
        self.destinations = result.destinations
        old = self.state.settings
        selected = next((d for d in self.destinations if d.area_id == old.area_id and d.channel_id == old.channel_id), None)
        if selected:
            settings = replace(old, area_name=selected.area_name, channel_name=selected.channel_name)
        else:
            settings = replace(old, area_id=result.current_area_id, area_name=result.current_area_name, channel_id='', channel_name='')
        self.configure(settings)
        if settings.channel_id and (not self.state.connected):
            self.connect_current(clear=True)
        elif not settings.channel_id:
            self.gateway.disconnect()
            self.timeline = Timeline()
            self.state = reduce(self.state, 'connection', self.gateway.generation)
            self.state = reduce(self.state, 'status', '')
        self.render()

    def connect_current(self, *, clear):
        if not self.state.settings.is_ready:
            return
        if clear:
            self.timeline = Timeline()
        self._retry = False
        self.gateway.connect(self.state.settings)
        self.state = reduce(self.state, 'connection', self.gateway.generation)

    def gateway_event(self, event):
        if self._closing:
            return
        kind = event.kind
        values = event.values
        if kind == 'session':
            self.session_checked(values[0])
            return
        if kind == 'send_failed':
            outgoing = values[0]
            self.state = reduce(self.state, 'send_failed', ((outgoing.person_uid, outgoing.area_id, outgoing.channel_id), outgoing.text))
            self.notice('send_failed')
        elif event.generation != self.state.generation:
            return
        elif kind in {'timeline', 'live_timeline'}:
            notifications = self.timeline.merge(values[0], now=monotonic(), live=kind == 'live_timeline', reading=self.state.mode != 'passive')
            if notifications:
                win32.play_sound(self.state.settings.notification_sound)
        elif kind == 'status':
            self.state = reduce(self.state, 'connected', values[1])
        elif kind == 'error':
            self._retry = True
            self.state = reduce(self.state, 'connected', False)
        elif kind == 'inspection_error':
            self._inspection = False
            self.state = reduce(self.state, 'status', 'login')
        elif kind == 'history_error':
            self.notice('history_failed')
        self.render()

    def notice(self, key):
        self.tray.showMessage(tr('app'), tr(key))

    def open_settings(self):
        self.action('cancel')
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self.state.settings)
            self.settings_window.changed.connect(self.configure)
            self.settings_window.edit_requested.connect(lambda: self.action('adjust'))
            self.settings_window.recording.connect(self.pause_hotkeys)
            self.settings_window.finished.connect(lambda _: self.render())
        self.settings_window.sync(self.state.settings)
        self.settings_window.set_update_status(self._update_status)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()
        self.render()

    def pause_hotkeys(self, paused):
        if self.hotkeys:
            try:
                self.hotkeys.set_paused(paused)
            except (OSError, ValueError):
                self.notice('hotkey_failed')

    def check_update(self):
        if not updater.is_packaged():
            return
        root = self.root
        emit = self.bridge.update.emit

        def run():
            try:
                updater.stage_update(__version__, root, progress=emit)
            except Exception:
                emit(updater.UpdateProgress('update_failed'))
        threading.Thread(target=run, name='typeslip-update', daemon=True).start()

    def update_progress(self, progress):
        if self._closing:
            return
        self._update_status = tr(progress.phase)
        if self.settings_window:
            self.settings_window.set_update_status(self._update_status)
        if progress.phase == 'ready':
            self.tray.showMessage(tr('app'), self._update_status)

    def shutdown(self):
        if self._closing:
            return
        self._closing = True
        self.poll.stop()
        self.startup.stop()
        self.update_timer.stop()
        if self.hotkeys:
            self.hotkeys.close()
        if self.wheel_hook:
            self.wheel_hook.close()
        self.gateway.close()
        self.hud.close()
        self.tray.hide()
        if self.settings_window:
            self.settings_window.close()
        self.application.quit()

def main() -> int:
    result = updater.handle_update_arguments(sys.argv[1:])
    if result is not None:
        return result
    if os.name != 'nt':
        raise SystemExit('TypeSlip requires Windows')
    application = QApplication(sys.argv)
    application.setApplicationName(tr('app'))
    application.setOrganizationName('RinChan')
    application.setWindowIcon(app_icon())
    instance = SingleInstance(state_root())
    if not instance.acquire():
        return 0
    try:
        if updater.start_pending_update(state_root(), __version__):
            return 0
        controller = AppController(application)
        instance.activated.connect(controller.open_settings)
        application.aboutToQuit.connect(controller.shutdown)
        return application.exec()
    finally:
        instance.close()
if __name__ == '__main__':
    raise SystemExit(main())
