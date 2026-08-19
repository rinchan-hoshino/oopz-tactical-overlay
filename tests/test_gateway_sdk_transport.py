from dataclasses import fields

from oopz_overlay.gateway import GatewayCallbacks
from oopz_overlay.settings import AppSettings


def test_gateway_callbacks_have_no_ui_automation_channel_callback() -> None:
    assert [item.name for item in fields(GatewayCallbacks)] == [
        "timeline",
        "status",
        "error",
    ]


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
