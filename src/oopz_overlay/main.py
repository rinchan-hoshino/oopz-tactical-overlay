from __future__ import annotations

import importlib
import os
import sys
import threading
from collections import defaultdict, deque
from time import monotonic
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QSystemTrayIcon,
)

from . import __version__
from .chat import ChatMessage
from .dpapi import WindowsDpapiProtector
from .gateway import GatewayCallbacks, GatewayEvent, GatewayRuntime, LoginResult
from .local_session import LocalSessionError, load_oopz_local_session
from .instance import SingleInstance
from .settings import AppSettings, JsonSettingsStore
from .updater import (
    UpdateProgress,
    cleanup_updater_later,
    is_packaged,
    run_update_helper,
    stage_update,
    start_pending_update,
)
from .widgets import OverlayWindow
from .ui_common import APP_NAME, FONT_FAMILY, app_icon
from .settings_dialog import SetupDialog
from .win32_input import GlobalHotkeyRegistration, GlobalWheelRegistration


class Bridge(QObject):
    gateway_event = Signal(object)
    session_checked = Signal(object)
    wheel_delta = Signal(int)
    input_error = Signal(str)
    timeline = Signal(object)
    live_timeline = Signal(object)
    status = Signal(str, bool)
    error = Signal(str)
    send_error = Signal(str)
    login_result = Signal(object)
    update_ready = Signal(str)
    update_progress = Signal(object)


class AppController(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        self.bridge = Bridge()
        self.overlay = OverlayWindow()
        self.setup_dialog: SetupDialog | None = None
        self._shutting_down = False
        self.state_root = self._state_root()
        self.store = JsonSettingsStore(
            self.state_root / "state.bin", WindowsDpapiProtector()
        )
        try:
            self.settings = self.store.load()
        except (OSError, ValueError, TypeError, UnicodeError):
            self.settings = AppSettings()
        self._connected_key = ()
        self._session_reading = False
        self._session_refresh_pending = False
        self._login_serial = 0
        self._failed_drafts = defaultdict(deque)
        self._warnings: dict[str, float] = {}
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(250)
        self._save_timer.timeout.connect(self._save_settings)
        self.overlay.configure(self.settings)
        self.hotkeys = GlobalHotkeyRegistration(int(self.overlay.winId()))
        self._hotkey_startup_error = ""
        try:
            self.hotkeys.configure(
                self.settings.hotkey,
                self.settings.visibility_hotkey,
            )
        except (OSError, ValueError) as exc:
            self._hotkey_startup_error = str(exc)
        self.wheel: GlobalWheelRegistration | None = None
        try:
            self.wheel = GlobalWheelRegistration(
                self.bridge.wheel_delta.emit,
                window_id=int(self.overlay.winId()),
                on_error=self.bridge.input_error.emit,
            )
            self.overlay.interaction_changed.connect(self.wheel.set_enabled)
        except OSError as exc:
            detail = str(exc)
            self._hotkey_startup_error = "；".join(
                part for part in (self._hotkey_startup_error, detail) if part
            )
        self.gateway = GatewayRuntime(
            GatewayCallbacks(
                timeline=self.bridge.timeline.emit,
                live_timeline=self.bridge.live_timeline.emit,
                status=self.bridge.status.emit,
                error=self.bridge.error.emit,
                send_error=self.bridge.send_error.emit,
                event=self.bridge.gateway_event.emit,
            )
        )

        self.bridge.timeline.connect(self.overlay.merge_messages)
        self.bridge.live_timeline.connect(self.overlay.merge_live_messages)
        self.bridge.status.connect(self.overlay.set_connection_status)
        self.bridge.error.connect(self._on_error)
        self.bridge.send_error.connect(self._on_send_error)
        self.bridge.login_result.connect(self._on_login_result)
        self.bridge.gateway_event.connect(self._on_gateway_event)
        self.bridge.session_checked.connect(self._on_session_checked)
        self.bridge.wheel_delta.connect(self.overlay.handle_global_wheel)
        self.bridge.input_error.connect(self._show_warning)
        self.bridge.update_ready.connect(self._on_update_ready)
        self.bridge.update_progress.connect(self._on_update_progress)
        self.overlay.send_requested.connect(self.gateway.send)
        self.overlay.edit_committed.connect(self._edit_committed)
        self.overlay.edit_cancelled.connect(self._edit_cancelled)
        self.overlay.activation_hotkey_pressed.connect(self._activate_overlay)
        self.overlay.visibility_hotkey_pressed.connect(self._toggle_visibility)
        self.overlay.activation_failed.connect(self._show_warning)

        self._update_status = "等待检查更新"
        if (self.state_root / "update-error.json").is_file():
            self._update_status = "上次更新失败，本次启动后会重试"
        self.tray = QSystemTrayIcon(self._icon(), self)
        self._update_tray_tooltip()
        menu = QMenu()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self.shutdown)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        self._session_timer = QTimer(self)
        self._session_timer.setInterval(5000)
        self._session_timer.timeout.connect(lambda: self._read_session(force=False))
        self._session_timer.start()

        if self._hotkey_startup_error:
            QTimer.singleShot(0, self._show_hotkey_startup_error)
        QTimer.singleShot(1800, self._check_update)

        if self.settings.area_id and self.settings.channel_id:
            QTimer.singleShot(80, self._import_session)
        else:
            QTimer.singleShot(0, self.open_settings)

    @staticmethod
    def _state_root() -> Path:
        root = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        return root / "RinChan" / "OopzTacticalOverlay"

    @classmethod
    def _state_path(cls) -> Path:
        return cls._state_root() / "state.bin"

    @staticmethod
    def _icon() -> QIcon:
        return app_icon()

    def _activate_overlay(self) -> None:
        if self.overlay.is_active or self.overlay.is_editing:
            return
        if not self.overlay.is_connected:
            self._show_warning("尚未连接 Oopz，请从托盘打开设置查看连接状态。")
            return
        if self.setup_dialog is not None:
            self.setup_dialog.hide()
        self.overlay.show_overlay()
        key = (
            self.settings.person_uid,
            self.settings.area_id,
            self.settings.channel_id,
        )
        if self.overlay.is_active and self._failed_drafts[key]:
            self.overlay.input.setText(self._failed_drafts[key].popleft())
            self.overlay.composer.set_failed(True)
            self.overlay.input.end(False)

    def _toggle_visibility(self) -> None:
        if self.overlay.is_active or self.overlay.is_editing:
            return
        self.overlay.toggle_visibility()

    def _show_hotkey_startup_error(self) -> None:
        self.open_settings()
        if self.setup_dialog is not None:
            self.setup_dialog.show_error(self._hotkey_startup_error)

    def _connect_current(self) -> None:
        if not self.settings.is_ready:
            return
        self.overlay.clear_messages()
        self.overlay.set_connection_status(
            f"正在连接 #{self.settings.channel_name}…",
            False,
        )
        self._connected_key = self._connection_key(self.settings)
        self.gateway.connect(self.settings)

    @staticmethod
    def _connection_key(settings: AppSettings) -> tuple:
        return (
            settings.person_uid,
            settings.area_id,
            settings.channel_id,
            settings.device_id,
            settings.jwt_token,
            settings.app_version,
        )

    def open_settings(self) -> None:
        if self.overlay.is_active:
            self.overlay.hide_overlay()
        if self.setup_dialog is not None:
            if self.overlay.is_editing:
                self.overlay.cancel_edit()
            self.setup_dialog.show()
            self.setup_dialog.raise_()
            self.setup_dialog.activateWindow()
            return
        dialog = SetupDialog(self.settings)
        dialog.session_requested.connect(self._import_session)
        dialog.settings_changed.connect(self._configured)
        dialog.edit_requested.connect(self._begin_edit)
        dialog.recording_changed.connect(self._pause_hotkeys)
        dialog.finished.connect(self._setup_finished)
        self.setup_dialog = dialog
        dialog.set_update_status(self._update_status)
        dialog.set_connection_status(
            self.overlay.status.text() or "未连接", self.overlay.is_connected
        )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        QTimer.singleShot(0, self._import_session)

    def _import_session(self) -> None:
        self._read_session(force=True)

    def _read_session(self, *, force: bool) -> None:
        if self._shutting_down:
            return
        if self._session_reading:
            self._session_refresh_pending |= force
            return
        self._session_reading = True

        def run() -> None:
            try:
                session = load_oopz_local_session()
                self.bridge.session_checked.emit((session, "", force))
            except (LocalSessionError, OSError, ValueError) as exc:
                self.bridge.session_checked.emit((None, str(exc), force))

        threading.Thread(target=run, name="oopz-local-session", daemon=True).start()

    def _on_session_checked(self, result) -> None:
        self._session_reading = False
        if self._shutting_down:
            return
        session, error, force = result
        force |= self._session_refresh_pending
        self._session_refresh_pending = False
        if session is None:
            self._login_serial += 1
            if self._connected_key or self.settings.has_credentials:
                self.gateway.disconnect()
                self._connected_key = ()
                self.settings = replace(
                    self.settings, device_id="", person_uid="", jwt_token=""
                )
                if self.setup_dialog is not None:
                    self.setup_dialog.sync_settings(self.settings)
                self._on_error(error)
            if self.setup_dialog is not None:
                self.setup_dialog.show_error(error)
                self.setup_dialog.set_connection_status(error, False)
            return
        current = replace(
            self.settings,
            device_id=session.device_id,
            person_uid=session.person_uid,
            jwt_token=session.jwt_token,
            app_version=session.app_version,
        )
        if not force and (
            self._connection_key(current) == self._connected_key
            or (
                not current.channel_id
                and current.has_credentials
                and current.jwt_token == self.settings.jwt_token
            )
        ):
            return
        self._login_serial += 1
        serial = self._login_serial
        self.gateway.inspect_session(
            current,
            success=lambda result: self.bridge.login_result.emit((serial, result)),
        )

    def _on_login_result(self, result: LoginResult) -> None:
        if self._shutting_down:
            return
        if isinstance(result, tuple):
            serial, result = result
            if serial != self._login_serial:
                return
        if not result.settings.channel_id:
            self._configured(
                replace(
                    self.settings,
                    device_id=result.settings.device_id,
                    person_uid=result.settings.person_uid,
                    jwt_token=result.settings.jwt_token,
                    app_version=result.settings.app_version,
                    area_id=result.settings.area_id,
                    area_name=result.settings.area_name,
                    channel_id="",
                    channel_name="",
                )
            )
            if self.setup_dialog is None:
                self.open_settings()
            if self.setup_dialog is not None:
                self.setup_dialog.apply_login_result(result)
            return
        selected = next(
            (
                item
                for item in result.destinations
                if item.channel_id == result.settings.channel_id
            ),
            None,
        )
        if selected is None:
            self._configured(
                replace(
                    self.settings,
                    device_id=result.settings.device_id,
                    person_uid=result.settings.person_uid,
                    jwt_token=result.settings.jwt_token,
                    app_version=result.settings.app_version,
                    channel_id="",
                    channel_name="",
                )
            )
            if self.setup_dialog is None:
                self.open_settings()
            if self.setup_dialog is not None:
                self.setup_dialog.apply_login_result(result)
            return
        settings = replace(
            self.settings,
            device_id=result.settings.device_id,
            person_uid=result.settings.person_uid,
            jwt_token=result.settings.jwt_token,
            app_version=result.settings.app_version,
            area_id=selected.area_id,
            area_name=selected.area_name,
            channel_id=selected.channel_id,
            channel_name=selected.channel_name,
        )
        self._configured(settings)
        if self.setup_dialog is not None:
            self.setup_dialog.apply_login_result(
                replace(result, settings=self.settings)
            )

    def _configured(self, settings: AppSettings) -> None:
        if (settings.area_id, settings.channel_id) != (
            self.settings.area_id,
            self.settings.channel_id,
        ):
            self._login_serial += 1
        try:
            self.hotkeys.configure(settings.hotkey, settings.visibility_hotkey)
        except (OSError, ValueError) as exc:
            if self.setup_dialog is not None:
                self.setup_dialog.sync_settings(self.settings)
                self.setup_dialog.show_error(str(exc))
            return
        next_connection = self._connection_key(settings)
        self.settings = settings
        self._save_timer.start()
        self.overlay.configure(settings)
        if settings.is_ready and next_connection != self._connected_key:
            self._connect_current()
        elif not settings.is_ready:
            self._connected_key = ()
            self.gateway.disconnect()
            self.overlay.set_connection_status("请选择 Oopz 文字频道", False)

    def _save_settings(self) -> None:
        try:
            self.store.save(self.settings)
        except OSError:
            self._show_warning("设置暂时无法保存，请检查磁盘空间和文件权限。")

    def _pause_hotkeys(self, paused: bool) -> None:
        try:
            self.hotkeys.set_paused(paused)
        except (OSError, ValueError) as exc:
            self._show_warning(str(exc))

    def _on_gateway_event(self, event: GatewayEvent) -> None:
        if self._shutting_down:
            return
        if event.kind == "send_failed":
            outgoing = event.values[0]
            key = (outgoing.person_uid, outgoing.area_id, outgoing.channel_id)
            self._failed_drafts[key].append(outgoing.text)
            self._on_send_error(outgoing.error)
            return
        if event.generation != self.gateway.generation:
            return
        if event.kind == "status":
            text, connected = event.values
            was_connected = self.overlay.is_connected
            self.overlay.set_connection_status(text, connected)
            if self.setup_dialog is not None:
                self.setup_dialog.set_connection_status(text, connected)
            if was_connected and not connected:
                self._show_warning(text)
        elif event.kind == "timeline":
            self.overlay.merge_messages(event.values[0])
        elif event.kind == "live_timeline":
            self.overlay.merge_live_messages(event.values[0])
        elif event.kind == "error":
            self._connected_key = ()
            self._on_error(event.values[0])
        elif event.kind in {"inspection_error", "history_error"}:
            if self.setup_dialog is not None:
                self.setup_dialog.show_error(event.values[0])
            self._show_warning(event.values[0])

    def _begin_edit(self) -> None:
        self.overlay.begin_edit_mode()

    def _edit_committed(
        self,
        x: float,
        y: float,
        width: int,
        height: int,
    ) -> None:
        self._configured(
            replace(
                self.settings,
                position_x=x,
                position_y=y,
                overlay_width=width,
                overlay_height=height,
                screen_name=self.overlay.screen().name(),
            )
        )
        if self.setup_dialog is not None:
            self.setup_dialog.sync_settings(self.settings)
            self.setup_dialog.show()
            self.setup_dialog.raise_()

    def _edit_cancelled(self) -> None:
        if self.setup_dialog is not None:
            self.setup_dialog.show()
            self.setup_dialog.raise_()

    def _setup_finished(self) -> None:
        self._pause_hotkeys(False)
        if self.setup_dialog is not None:
            self.setup_dialog.deleteLater()
        self.setup_dialog = None

    def _on_error(self, text: str) -> None:
        self.overlay.set_connection_status(text, False)
        if self.setup_dialog is not None and self.setup_dialog.isVisible():
            self.setup_dialog.show_error(text)
        self._show_warning(text)

    def _on_send_error(self, text: str) -> None:
        self._show_warning(f"消息发送失败：{text}")

    def _show_warning(self, text: str) -> None:
        now = monotonic()
        if now - self._warnings.get(text, -60) < 30:
            return
        self._warnings = {
            key: value for key, value in self._warnings.items() if now - value < 60
        }
        self._warnings[text] = now
        self.tray.showMessage(
            APP_NAME,
            text,
            QSystemTrayIcon.MessageIcon.Warning,
            5000,
        )

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.open_settings()

    def _check_update(self) -> None:
        if not is_packaged():
            return

        def run() -> None:
            try:
                manifest = stage_update(
                    __version__,
                    self.state_root,
                    progress=self.bridge.update_progress.emit,
                )
            except (OSError, ValueError):
                self.bridge.update_progress.emit(UpdateProgress("failed"))
                return
            if manifest is not None:
                self.bridge.update_ready.emit(manifest.version)

        threading.Thread(target=run, name="update-check", daemon=True).start()

    def _on_update_progress(self, progress: UpdateProgress) -> None:
        if progress.phase == "checking":
            text = "正在检查更新"
        elif progress.phase == "current":
            text = f"已是最新版 v{progress.version}"
        elif progress.phase == "downloading":
            percent = min(100, progress.downloaded * 100 // max(1, progress.total))
            text = f"正在下载 v{progress.version} · {percent}%"
        elif progress.phase == "ready":
            text = f"v{progress.version} 已下载，重启后更新"
        else:
            text = "检查更新失败，下次启动重试"
        self._update_status = text
        if progress.phase in {"current", "ready"}:
            (self.state_root / "update-error.json").unlink(missing_ok=True)
        self._update_tray_tooltip()
        if self.setup_dialog is not None:
            self.setup_dialog.set_update_status(text)

    def _update_tray_tooltip(self) -> None:
        self.tray.setToolTip(f"{APP_NAME} v{__version__}\n{self._update_status}")

    def _on_update_ready(self, version: str) -> None:
        self.tray.showMessage(
            APP_NAME,
            f"{version} 已下载，将在下次启动时自动更新。",
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save_settings()
        self._session_timer.stop()
        self.hotkeys.close()
        if self.wheel is not None:
            self.wheel.close()
        self.overlay.hide()
        self.tray.hide()
        self.gateway.close()
        self.app.quit()


def _demo_overlay() -> OverlayWindow:
    overlay = OverlayWindow()
    overlay.set_connection_status("#塔科夫战术", True)
    overlay.merge_messages(
        [
            ChatMessage(
                "demo-1",
                1_775_000_000_000_000,
                "user-1",
                "队友A",
                "二楼窗口一个",
                False,
            ),
            ChatMessage(
                "demo-2",
                1_775_000_005_000_000,
                "user-2",
                "玩家",
                "收到，我绕右侧",
                True,
            ),
            ChatMessage(
                "demo-3",
                1_775_000_009_000_000,
                "user-1",
                "队友A",
                "等一下，楼梯有脚步",
                False,
            ),
        ]
    )
    return overlay


def _render_preview(app: QApplication, path: Path) -> int:
    overlay = _demo_overlay()
    overlay.show_overlay()
    app.processEvents()
    path.parent.mkdir(parents=True, exist_ok=True)
    return 0 if overlay.grab().save(str(path), "PNG") else 5


def _smoke_test(app: QApplication) -> int:
    overlay = OverlayWindow()
    overlay.set_connection_status("#塔科夫", True)
    overlay.show_overlay()
    app.processEvents()
    if not overlay.isVisible():
        return 2
    overlay.hide_overlay()

    dialog = SetupDialog(AppSettings())
    dialog.show()
    app.processEvents()
    if not dialog.isVisible():
        return 3
    dialog.close()

    with TemporaryDirectory() as directory:
        store = JsonSettingsStore(
            Path(directory) / "state.bin",
            WindowsDpapiProtector(),
        )
        expected = AppSettings()
        store.save(expected)
        if store.load() != expected:
            return 4

    with TemporaryDirectory() as directory:
        previous_local_app_data = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = directory
        try:
            controller = AppController(app)
            if not controller.tray.isVisible():
                return 5
            controller.shutdown()
        finally:
            if previous_local_app_data is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = previous_local_app_data
    return 0


def _render_settings(app: QApplication, path: Path) -> int:
    settings = AppSettings(
        area_id="preview",
        area_name="猫尾服务器",
        channel_id="preview",
        channel_name="塔科夫",
    )
    dialog = SetupDialog(settings)
    dialog.set_connection_status("# 塔科夫", True)
    dialog.show()
    app.processEvents()
    path.parent.mkdir(parents=True, exist_ok=True)
    return 0 if dialog.grab().save(str(path), "PNG") else 5


def _close_onefile_splash() -> None:
    parent_process = os.environ.get("NUITKA_ONEFILE_PARENT", "").strip()
    if parent_process.isdigit():
        splash_feedback = (
            Path(gettempdir()) / f"onefile_{parent_process}_splash_feedback.tmp"
        )
        splash_feedback.unlink(missing_ok=True)


def _sdk_import_probe() -> int:
    importlib.import_module("oopz_sdk")
    importlib.import_module("oopz_sdk.client.rest")
    importlib.import_module("oopz_sdk.client.ws")
    return 0


def main() -> int:
    if os.name != "nt":
        raise SystemExit("纸条目前仅支持 Windows。")
    arguments = sys.argv[1:]
    if "--apply-update" in arguments:
        index = arguments.index("--apply-update")
        return run_update_helper(arguments[index + 1 : index + 7])
    if "--cleanup-updater" in arguments:
        index = arguments.index("--cleanup-updater")
        if index + 1 < len(arguments):
            cleanup_updater_later(Path(arguments[index + 1]))
    if "--sdk-import-probe" in arguments:
        _close_onefile_splash()
        return _sdk_import_probe()
    state_root = AppController._state_root()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())
    app.setOrganizationName("RinChan")
    app.setFont(QFont(FONT_FAMILY))
    if "--smoke-test" in sys.argv:
        _close_onefile_splash()
        return _smoke_test(app)
    if "--render-preview" in sys.argv:
        _close_onefile_splash()
        index = sys.argv.index("--render-preview")
        if index + 1 >= len(sys.argv):
            return 6
        return _render_preview(app, Path(sys.argv[index + 1]))
    if "--render-settings" in sys.argv:
        index = sys.argv.index("--render-settings")
        if index + 1 >= len(sys.argv):
            return 6
        return _render_settings(app, Path(sys.argv[index + 1]))
    instance = SingleInstance(state_root)
    if not instance.acquire():
        _close_onefile_splash()
        return 0
    if start_pending_update(state_root, __version__):
        instance.close()
        return 0
    controller = AppController(app)
    instance.activated.connect(controller.open_settings)
    app.aboutToQuit.connect(instance.close)
    app.aboutToQuit.connect(controller.gateway.close)
    QTimer.singleShot(100, _close_onefile_splash)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
