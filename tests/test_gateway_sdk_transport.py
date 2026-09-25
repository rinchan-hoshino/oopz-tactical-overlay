from dataclasses import fields
from types import SimpleNamespace

from oopz_overlay.gateway import GatewayCallbacks, GatewayRuntime
from oopz_overlay.settings import AppSettings


def test_gateway_callbacks_have_no_ui_automation_channel_callback() -> None:
    assert [item.name for item in fields(GatewayCallbacks)] == [
        "timeline",
        "live_timeline",
        "status",
        "error",
        "send_error",
        "event",
    ]


def test_send_failure_uses_scoped_callback_instead_of_connection_error() -> None:
    connection_errors: list[str] = []
    send_errors: list[str] = []
    runtime = object.__new__(GatewayRuntime)
    runtime.callbacks = SimpleNamespace(
        error=connection_errors.append,
        send_error=send_errors.append,
        event=None,
    )
    runtime._generation = 0
    runtime._settings = AppSettings()
    runtime._closed = False
    submitted = []

    def submit(coroutine, *, success=None, error=None) -> None:
        submitted.append(error)
        coroutine.close()
        error("消息被拒绝")

    runtime._submit = submit
    runtime.send("违禁词")

    assert len(submitted) == 1
    assert send_errors == ["消息被拒绝"]
    assert connection_errors == []


def test_manual_destination_is_part_of_ready_state() -> None:
    session = {
        "device_id": "device",
        "person_uid": "person",
        "jwt_token": "token",
    }

    assert not AppSettings(**session).is_ready
    assert AppSettings(
        **session,
        area_id="area",
        channel_id="channel",
    ).is_ready
