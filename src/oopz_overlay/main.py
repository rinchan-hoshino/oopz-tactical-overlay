from __future__ import annotations

import importlib
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
from .gateway import GatewayCallbacks, GatewayRuntime
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
from .win32_input import GlobalHotkeyRegistration


class Bridge(QObject):
    timeline = Signal(object)
    status = Signal(str, bool)
    error = Signal(str)
    channel_changed = Signal(str)
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
        self.current_channel = ""
        self.overlay.configure(self.settings)
        self.hotkeys = GlobalHotkeyRegistration(int(self.overlay.winId()))
        self._hotkey_startup_error = ""
        try:
            self.hotkeys.configure(
                self.settings.hotkey,
                self.settings.visibility_hotkey,
            )
        except OSError as exc:
            self._hotkey_startup_error = str(exc)
        self.gateway = GatewayRuntime(
            GatewayCallbacks(
                timeline=self.bridge.timeline.emit,
                status=self.bridge.status.emit,
                error=self.bridge.error.emit,
                channel=self.bridge.channel_changed.emit,
            )
        )

        self.bridge.timeline.connect(self.overlay.merge_messages)
        self.bridge.status.connect(self.overlay.set_connection_status)
        self.bridge.error.connect(self._on_error)
        self.bridge.channel_changed.connect(self._channel_changed)
        self.bridge.update_ready.connect(self._on_update_ready)
        self.bridge.update_progress.connect(self._on_update_progress)
        self.overlay.send_requested.connect(self.gateway.send)
        self.overlay.edit_committed.connect(self._edit_committed)
        self.overlay.edit_cancelled.connect(self._edit_cancelled)
        self.overlay.activation_hotkey_pressed.connect(self._activate_overlay)
        self.overlay.visibility_hotkey_pressed.connect(self._toggle_visibility)

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

        if self._hotkey_startup_error:
            QTimer.singleShot(0, self._show_hotkey_startup_error)
        QTimer.singleShot(1800, self._check_update)

        QTimer.singleShot(80, self._connect_current)

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

    def _activate_overlay(self) -> None:
        if self.overlay.is_active or self.overlay.is_editing:
            return
        if self.setup_dialog is not None:
            self.setup_dialog.hide()
        self.overlay.show_overlay()

    def _toggle_visibility(self) -> None:
        if self.overlay.is_active or self.overlay.is_editing:
            return
        self.overlay.toggle_visibility()

    def _show_hotkey_startup_error(self) -> None:
        self.open_settings()
        if self.setup_dialog is not None:
            self.setup_dialog.show_error(self._hotkey_startup_error)

    def _connect_current(self) -> None:
        self.overlay.clear_messages()
        self.overlay.set_connection_status("正在连接 Oopz…", False)
        self.gateway.connect()

    def open_settings(self) -> None:
        if self.overlay.is_active:
            self.overlay.hide_overlay()
        if self.setup_dialog is not None and self.setup_dialog.isVisible():
            self.setup_dialog.raise_()
            self.setup_dialog.activateWindow()
            return
        dialog = SetupDialog(self.settings)
        dialog.settings_changed.connect(self._configured)
        dialog.edit_requested.connect(self._begin_edit)
        dialog.finished.connect(self._setup_finished)
        self.setup_dialog = dialog
        dialog.set_update_status(self._update_status)
        dialog.set_current_channel(
            self.current_channel,
            connected=bool(self.current_channel),
        )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _configured(self, settings: AppSettings) -> None:
        try:
            self.hotkeys.configure(settings.hotkey, settings.visibility_hotkey)
        except OSError as exc:
            if self.setup_dialog is not None:
                self.setup_dialog.show_error(str(exc))
            return
        self.settings = settings
        self.store.save(settings)
        self.overlay.configure(settings)

    def _channel_changed(self, channel_name: str) -> None:
        if channel_name == self.current_channel:
            return
        self.current_channel = channel_name
        self.overlay.clear_messages()
        if channel_name:
            self.overlay.set_connection_status(f"#{channel_name}", True)
        if self.setup_dialog is not None:
            self.setup_dialog.set_current_channel(
                channel_name,
                connected=bool(channel_name),
            )

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
        self.tray.setToolTip(f"Oopz 战术对话栏 v{__version__}\n{self._update_status}")

    def _on_update_ready(self, version: str) -> None:
        self.tray.showMessage(
            "Oopz Tactical Link",
            f"{version} 已下载，将在下次启动时自动更新。",
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )

    def shutdown(self) -> None:
        self.hotkeys.close()
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


def _close_onefile_splash() -> None:
    parent_process = os.environ.get("NUITKA_ONEFILE_PARENT", "").strip()
    if parent_process.isdigit():
        splash_feedback = (
            Path(gettempdir()) / f"onefile_{parent_process}_splash_feedback.tmp"
        )
        splash_feedback.unlink(missing_ok=True)


def _automation_import_probe() -> int:
    importlib.import_module("comtypes.stream")
    importlib.import_module("uiautomation")
    return 0


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
    if "--automation-import-probe" in arguments:
        _close_onefile_splash()
        return _automation_import_probe()
    state_root = AppController._state_root()
    if start_pending_update(state_root, __version__):
        return 0

    app = QApplication(sys.argv)
    app.setApplicationName("Oopz Tactical Overlay")
    app.setOrganizationName("RinChan")
    app.setStyle("Fusion")
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
    controller = AppController(app)
    app.aboutToQuit.connect(controller.gateway.close)
    QTimer.singleShot(100, _close_onefile_splash)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
