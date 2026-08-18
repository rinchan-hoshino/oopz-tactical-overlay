from __future__ import annotations

import os
import sys
import threading
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QSystemTrayIcon,
)

from . import __version__
from .chat import ChatMessage
from .dpapi import WindowsDpapiProtector
from .gateway import GatewayCallbacks, GatewayRuntime, LoginResult
from .local_session import LocalSessionError, load_oopz_local_session
from .settings import AppSettings, JsonSettingsStore
from .updater import (
    UpdateProgress,
    cleanup_updater_later,
    is_packaged,
    run_update_helper,
    stage_update,
    start_pending_update,
)
from .widgets import FONT_FAMILY, OverlayWindow, SetupDialog
from .win32_input import GlobalHotkeyMonitor


class Bridge(QObject):
    timeline = Signal(object)
    status = Signal(str, bool)
    error = Signal(str)
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
        self.state_root = self._state_root()
        self.store = JsonSettingsStore(
            self.state_root / "state.bin", WindowsDpapiProtector()
        )
        try:
            self.settings = self.store.load()
        except (OSError, ValueError, UnicodeError):
            self.settings = AppSettings()
        self._connected_key = ("", "", "")
        self.overlay.configure(self.settings)

        self.monitor = GlobalHotkeyMonitor()
        self.gateway = GatewayRuntime(
            GatewayCallbacks(
                timeline=self.bridge.timeline.emit,
                status=self.bridge.status.emit,
                error=self.bridge.error.emit,
            )
        )

        self.bridge.timeline.connect(self.overlay.merge_messages)
        self.bridge.status.connect(self.overlay.set_connection_status)
        self.bridge.error.connect(self._on_error)
        self.bridge.login_result.connect(self._on_login_result)
        self.bridge.update_ready.connect(self._on_update_ready)
        self.bridge.update_progress.connect(self._on_update_progress)
        self.overlay.send_requested.connect(self.gateway.send)
        self.overlay.position_changed.connect(self._position_changed)
        self.overlay.size_changed.connect(self._size_changed)

        self._update_status = "更新 // 等待自动检查"
        if (self.state_root / "update-error.json").is_file():
            self._update_status = "更新 // 上次应用失败，已恢复运行并会重试"
        self.tray = QSystemTrayIcon(self._icon(), self)
        self._update_tray_tooltip()
        menu = QMenu()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self.shutdown)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

        self.input_timer = QTimer(self)
        self.input_timer.setInterval(18)
        self.input_timer.timeout.connect(self._poll_hotkey)
        self.input_timer.start()

        QTimer.singleShot(1800, self._check_update)

        if self.settings.is_ready:
            self._import_session()
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
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#d5a84b"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(4, 4, 56, 56, 14, 14)
        painter.setPen(QColor("#17130b"))
        font = QFont(FONT_FAMILY, 30, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "O")
        painter.end()
        return QIcon(pixmap)

    def _poll_hotkey(self) -> None:
        if self.overlay.is_active:
            return
        if self.monitor.hotkey_pressed(self.settings.hotkey):
            if self.setup_dialog is not None:
                self.setup_dialog.hide()
            self.overlay.show_overlay()

    def _connect_current(self) -> None:
        self.overlay.set_connection_status(
            f"正在连接 #{self.settings.channel_name}…", False
        )
        self._connected_key = (
            self.settings.person_uid,
            self.settings.area_id,
            self.settings.channel_id,
        )
        self.gateway.connect(self.settings)

    def open_settings(self) -> None:
        if self.overlay.is_active:
            self.overlay.hide_overlay()
        if self.setup_dialog is not None and self.setup_dialog.isVisible():
            self.setup_dialog.raise_()
            self.setup_dialog.activateWindow()
            return
        dialog = SetupDialog(self.settings)
        dialog.session_requested.connect(self._import_session)
        dialog.settings_changed.connect(self._configured)
        dialog.drag_requested.connect(self._begin_drag)
        dialog.finished.connect(self._setup_finished)
        self.setup_dialog = dialog
        dialog.set_update_status(self._update_status)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _import_session(self) -> None:
        try:
            settings = load_oopz_local_session()
        except LocalSessionError as exc:
            if self.setup_dialog is not None:
                self.setup_dialog.show_error(str(exc))
            return
        current = replace(
            self.settings,
            device_id=settings.device_id,
            person_uid=settings.person_uid,
            jwt_token=settings.jwt_token,
            app_version=settings.app_version,
        )
        self.gateway.inspect_session(current, success=self.bridge.login_result.emit)

    def _on_login_result(self, result: LoginResult) -> None:
        if self.setup_dialog is not None and self.setup_dialog.isVisible():
            self.setup_dialog.apply_login_result(result)
            return

        selected = next(
            (
                item
                for item in result.destinations
                if item.channel_id == result.settings.channel_id
            ),
            result.destinations[0] if result.destinations else None,
        )
        settings = result.settings
        if selected is not None:
            settings = replace(
                settings,
                area_id=selected.area_id,
                area_name=selected.area_name,
                channel_id=selected.channel_id,
                channel_name=selected.channel_name,
            )
        self._configured(settings)

    def _configured(self, settings: AppSettings) -> None:
        next_connection = (
            settings.person_uid,
            settings.area_id,
            settings.channel_id,
        )
        self.settings = settings
        self.store.save(settings)
        self.overlay.configure(settings)
        if settings.is_ready and next_connection != self._connected_key:
            self._connect_current()
        elif not settings.is_ready:
            self._connected_key = ("", "", "")
            self.gateway.disconnect()
            self.overlay.set_connection_status("未检测到当前服务器", False)

    def _begin_drag(self) -> None:
        if self.setup_dialog is not None:
            self.setup_dialog.close()
        self.overlay.begin_drag_mode()

    def _position_changed(self, x: float, y: float) -> None:
        self._configured(replace(self.settings, position_x=x, position_y=y))

    def _size_changed(self, width: int, height: int) -> None:
        self._configured(
            replace(self.settings, overlay_width=width, overlay_height=height)
        )

    def _setup_finished(self) -> None:
        self.setup_dialog = None

    def _on_error(self, text: str) -> None:
        self.overlay.set_connection_status(text, False)
        if self.setup_dialog is not None and self.setup_dialog.isVisible():
            self.setup_dialog.show_error(text)
        self.tray.showMessage(
            "Oopz 战术对话栏",
            text,
            QSystemTrayIcon.MessageIcon.Warning,
            5000,
        )
        if "重新登录" in text and (
            self.setup_dialog is None or not self.setup_dialog.isVisible()
        ):
            QTimer.singleShot(0, self.open_settings)

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
            text = "更新 // 正在检查…"
        elif progress.phase == "current":
            text = f"更新 // 已是最新版 v{progress.version}"
        elif progress.phase == "downloading":
            percent = min(100, progress.downloaded * 100 // max(1, progress.total))
            text = f"更新 // 正在下载 v{progress.version} · {percent}%"
        elif progress.phase == "ready":
            text = f"更新 // v{progress.version} 已下载，重启后应用"
        else:
            text = "更新 // 检查失败，下次启动重试"
        self._update_status = text
        if progress.phase in {"current", "ready"}:
            (self.state_root / "update-error.json").unlink(missing_ok=True)
        self._update_tray_tooltip()
        if self.setup_dialog is not None:
            self.setup_dialog.set_update_status(text)

    def _update_tray_tooltip(self) -> None:
        self.tray.setToolTip(f"Oopz 战术对话栏 v{__version__}\n{self._update_status}")

    def _on_update_ready(self, version: str) -> None:
        self.tray.showMessage(
            "Oopz Tactical Link",
            f"{version} 已下载，将在下次启动时自动更新。",
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )

    def shutdown(self) -> None:
        self.input_timer.stop()
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
                "demo-1", 1_775_000_000_000_000, "user-1", "澪子", "二楼窗口一个", False
            ),
            ChatMessage(
                "demo-2",
                1_775_000_005_000_000,
                "user-2",
                "黑夜",
                "收到，我绕右侧",
                True,
            ),
            ChatMessage(
                "demo-3",
                1_775_000_009_000_000,
                "user-1",
                "澪子",
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
        expected = AppSettings(
            device_id="device",
            person_uid="person",
            jwt_token="secret",
        )
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


def _close_onefile_splash() -> None:
    parent_process = os.environ.get("NUITKA_ONEFILE_PARENT", "").strip()
    if parent_process.isdigit():
        splash_feedback = (
            Path(gettempdir()) / f"onefile_{parent_process}_splash_feedback.tmp"
        )
        splash_feedback.unlink(missing_ok=True)


def main() -> int:
    if os.name != "nt":
        raise SystemExit("Oopz Tactical Overlay currently supports Windows only.")
    arguments = sys.argv[1:]
    if "--apply-update" in arguments:
        index = arguments.index("--apply-update")
        return run_update_helper(arguments[index + 1 : index + 7])
    if "--cleanup-updater" in arguments:
        index = arguments.index("--cleanup-updater")
        if index + 1 < len(arguments):
            cleanup_updater_later(Path(arguments[index + 1]))
    state_root = AppController._state_root()
    if start_pending_update(state_root, __version__):
        return 0

    app = QApplication(sys.argv)
    app.setApplicationName("Oopz Tactical Overlay")
    app.setOrganizationName("RinChan")
    app.setStyle("Fusion")
    app.setFont(QFont(FONT_FAMILY))
    if "--smoke-test" in sys.argv:
        return _smoke_test(app)
    if "--render-preview" in sys.argv:
        index = sys.argv.index("--render-preview")
        if index + 1 >= len(sys.argv):
            return 6
        return _render_preview(app, Path(sys.argv[index + 1]))
    controller = AppController(app)
    app.aboutToQuit.connect(controller.gateway.close)
    QTimer.singleShot(100, _close_onefile_splash)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
