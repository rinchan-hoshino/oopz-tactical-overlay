import pytest
from dataclasses import replace

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from oopz_overlay.chat import ChatMessage
from oopz_overlay.main import AppController, _close_onefile_splash
from oopz_overlay.settings import AppSettings
from oopz_overlay.gateway import Destination, GatewayEvent, LoginResult, OutgoingMessage


@pytest.fixture(autouse=True)
def isolated_platform(monkeypatch):
    class Hotkeys:
        def __init__(self, *_args):
            pass

        def configure(self, *_args):
            pass

        def set_paused(self, *_args):
            pass

        def close(self):
            pass

    class Protector:
        def protect(self, data):
            return data

        def unprotect(self, data):
            return data

    monkeypatch.setattr("oopz_overlay.main.GlobalHotkeyRegistration", Hotkeys)
    monkeypatch.setattr("oopz_overlay.main.WindowsDpapiProtector", Protector)
    monkeypatch.setattr(AppController, "_import_session", lambda self: None)


def test_app_controller_constructs_with_owned_state_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])

    controller = AppController(app)

    app.processEvents()
    assert controller.state_root == tmp_path / "RinChan" / "OopzTacticalOverlay"
    assert controller.tray.isVisible()
    assert controller._update_status == "等待检查更新"

    controller.overlay.set_connection_status("#塔科夫", True)
    controller.overlay.show_overlay()
    assert controller.overlay.is_active

    controller.open_settings()
    app.processEvents()
    assert not controller.overlay.is_active
    assert controller.setup_dialog is not None
    assert controller.setup_dialog.isVisible()
    controller._activate_overlay()
    app.processEvents()
    assert controller.overlay.is_active
    assert not controller.setup_dialog.isVisible()

    controller.overlay.hide_overlay()
    controller.setup_dialog.close()
    controller.shutdown()
    app.processEvents()


def test_sound_only_for_new_other_live_messages_in_current_generation(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    controller = AppController(app)
    calls = []
    monkeypatch.setattr("oopz_overlay.main.play_sound", calls.append)

    def deliver(kind, message, generation=None):
        controller._on_gateway_event(
            GatewayEvent(
                controller.gateway.generation if generation is None else generation,
                kind,
                ([message],),
            )
        )

    other = ChatMessage("off", 1, "other", "队友", "关闭时", False)
    deliver("live_timeline", other)
    assert calls == []
    controller.settings = replace(controller.settings, notification_sound="notify.wav")
    old = replace(other, message_id="history", text="历史")
    deliver("timeline", old)
    deliver("live_timeline", old)
    deliver("live_timeline", replace(other, message_id="mine", mine=True))
    deliver("live_timeline", replace(other, message_id="pending", pending=True))
    deliver("live_timeline", replace(other, message_id="failed", failed=True))
    deliver(
        "live_timeline",
        replace(other, message_id="stale"),
        controller.gateway.generation - 1,
    )
    assert calls == []
    fresh = replace(other, message_id="fresh", timestamp_us=2)
    deliver("live_timeline", fresh)
    deliver("live_timeline", fresh)
    deliver("live_timeline", replace(fresh, text="编辑已有消息"))
    assert calls == ["notify.wav"]
    controller.settings = replace(controller.settings, notification_sound="")
    deliver("live_timeline", replace(other, message_id="off-again"))
    assert calls == ["notify.wav"]
    controller.shutdown()
    app.processEvents()


def test_manual_channel_change_clears_timeline_and_reconnects(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    controller = AppController(app)
    connected: list[AppSettings] = []
    monkeypatch.setattr(controller.gateway, "connect", connected.append)
    monkeypatch.setattr(controller.hotkeys, "configure", lambda *_args: None)
    controller.overlay.merge_messages(
        [ChatMessage("old", 1, "u", "风屿", "旧频道消息", False)]
    )
    settings = AppSettings(
        device_id="device",
        person_uid="person",
        jwt_token="token",
        area_id="area",
        area_name="猫尾服务器",
        channel_id="strategy",
        channel_name="攻略",
    )

    controller._configured(settings)

    assert controller.overlay.timeline.items == ()
    assert connected == [settings]
    controller.shutdown()
    app.processEvents()


def test_send_rejection_keeps_the_channel_connected(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    controller = AppController(app)
    controller.overlay.configure(AppSettings(always_visible=True))
    controller.overlay.set_connection_status("#塔科夫", True)

    controller._on_send_error("Oopz：消息包含违禁词")
    app.processEvents()

    assert controller.overlay.is_connected
    assert controller.overlay.isVisible()
    controller.shutdown()
    app.processEvents()


def test_visibility_hotkey_toggles_the_passive_hud(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    controller = AppController(app)
    controller.settings = AppSettings(hotkey="F8", visibility_hotkey="F9")
    controller.overlay.configure(controller.settings)
    controller.overlay.set_connection_status("#塔科夫", True)
    controller._toggle_visibility()
    app.processEvents()

    assert controller.overlay.isHidden()
    controller.shutdown()
    app.processEvents()


def test_onefile_splash_feedback_is_removed_when_ui_is_ready(
    tmp_path, monkeypatch
) -> None:
    feedback = tmp_path / "onefile_4321_splash_feedback.tmp"
    feedback.write_text("")
    monkeypatch.setenv("NUITKA_ONEFILE_PARENT", "4321")
    monkeypatch.setattr("oopz_overlay.main.gettempdir", lambda: str(tmp_path))

    _close_onefile_splash()

    assert not feedback.exists()


def test_refreshing_credentials_connects_even_while_settings_are_visible(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    controller = AppController(app)
    connected = []
    monkeypatch.setattr(controller.gateway, "connect", connected.append)
    controller.settings = AppSettings(area_id="area", channel_id="text", font_size=18)
    controller.open_settings()
    result = LoginResult(
        AppSettings(
            device_id="device",
            person_uid="me",
            jwt_token="first",
            area_id="area",
            channel_id="text",
            channel_name="聊天",
        ),
        (Destination("area", "server", "text", "聊天"),),
        "area",
        "server",
        True,
    )
    controller._on_login_result(result)
    controller._on_login_result(
        replace(result, settings=replace(result.settings, jwt_token="refreshed"))
    )
    assert [settings.jwt_token for settings in connected] == ["first", "refreshed"]
    assert all(settings.font_size == 18 for settings in connected)
    controller.setup_dialog.close()
    controller.shutdown()


def test_old_queued_events_are_ignored_and_failed_draft_returns_to_its_channel(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    controller = AppController(app)
    controller.settings = AppSettings(
        person_uid="me", area_id="area", channel_id="text"
    )
    controller._on_gateway_event(
        GatewayEvent(
            -1, "timeline", ([ChatMessage("old", 1, "peer", "peer", "stale", False)],)
        )
    )
    assert not controller.overlay.timeline.items
    controller._on_gateway_event(
        GatewayEvent(
            -1,
            "send_failed",
            (OutgoingMessage("保留草稿😀", "area", "text", "me", "消息被拒绝"),),
        )
    )
    controller.overlay.set_connection_status("#text", True)
    controller._activate_overlay()
    assert controller.overlay.input.text() == "保留草稿😀"
    assert controller.overlay.input.cursorPosition() == 6
    controller.shutdown()


def test_manual_refresh_during_background_poll_is_not_lost(tmp_path, monkeypatch):
    from oopz_overlay.local_session import LocalOopzSession

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    controller = AppController(app)
    controller.settings = AppSettings(
        device_id="d", person_uid="p", jwt_token="t", area_id="a", channel_id="c"
    )
    controller._connected_key = controller._connection_key(controller.settings)
    controller._session_reading = True
    inspections = []
    monkeypatch.setattr(
        controller.gateway,
        "inspect_session",
        lambda settings, **kw: inspections.append(settings),
    )
    controller._read_session(force=True)
    controller._on_session_checked((LocalOopzSession("d", "p", "t"), "", False))
    assert len(inspections) == 1
    assert not controller._session_reading
    assert not controller._session_refresh_pending
    controller.shutdown()


def test_repeated_notification_is_coalesced(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    controller = AppController(app)
    notifications = []
    monkeypatch.setattr(
        controller.tray, "showMessage", lambda *args: notifications.append(args)
    )
    controller._show_warning("连接中断")
    controller._show_warning("连接中断")
    controller._show_warning("消息发送失败")
    assert len(notifications) == 2
    controller.shutdown()
